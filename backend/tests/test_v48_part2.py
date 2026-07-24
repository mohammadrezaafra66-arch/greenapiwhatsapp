"""V48 PART 2 — the unified all-accounts aggregation endpoint (`/accounts/overview`).

The overview is a PURE aggregation: every field must equal exactly what the existing per-page
source function returns for the same account. This test seeds a set of accounts covering every
role/state combination, then cross-checks each overview row field-by-field against a FRESH call
to the underlying source function (warmth_for_account, check_sender_eligibility, has_valid_override,
protection_snapshot, mesh_role_for, and the AccountIncident table) — NOT against hardcoded values —
so any future drift between the overview and a source page fails this test automatically.
"""
import uuid
from datetime import datetime, timedelta

import pytest

PREFIX = "V48OV-"


def _iid(suffix):
    return f"{PREFIX}{suffix}"


async def _cleanup():
    from app.database import AsyncSessionLocal
    from app.models.account import Account
    from app.models.incident import AccountIncident
    from app.models.warmup_mesh import WarmupEnrollment
    from app.models.warmup_helpers import WarmupHelper, WarmupTeamEnrollment, WarmupSenderConfig
    from sqlalchemy import select, delete
    async with AsyncSessionLocal() as db:
        accts = (await db.execute(
            select(Account).where(Account.instance_id.like(f"{PREFIX}%")))).scalars().all()
        ids = [a.id for a in accts]
        if ids:
            await db.execute(delete(AccountIncident).where(AccountIncident.account_id.in_(ids)))
        await db.execute(delete(WarmupEnrollment).where(WarmupEnrollment.instance_id.like(f"{PREFIX}%")))
        await db.execute(delete(WarmupHelper).where(WarmupHelper.sender_instance_id.like(f"{PREFIX}%")))
        await db.execute(delete(WarmupTeamEnrollment).where(WarmupTeamEnrollment.cold_instance_id.like(f"{PREFIX}%")))
        await db.execute(delete(WarmupSenderConfig).where(WarmupSenderConfig.sender_instance_id.like(f"{PREFIX}%")))
        await db.execute(delete(Account).where(Account.instance_id.like(f"{PREFIX}%")))
        await db.commit()


def _acct(suffix, created_days_ago, **kw):
    from app.models.account import Account, AccountStatus
    base = dict(
        id=uuid.uuid4(), name=f"acct-{suffix}", instance_id=_iid(suffix),
        api_token="tok", status=AccountStatus.active,
        phone="98912" + suffix.replace("-", "")[:7].ljust(7, "0"),
        sent_today=1, received_today=2, is_warm_peer=False, incident_count_7d=0,
        created_at=datetime.utcnow() - timedelta(days=created_days_ago),
    )
    base.update(kw)
    return Account(**base)


@pytest.mark.asyncio
async def test_overview_matches_every_source_function(monkeypatch):
    from app.database import AsyncSessionLocal, engine
    from app.models.account import Account
    from app.models.incident import AccountIncident
    from app.models.warmup_mesh import WarmupEnrollment
    from app.models.warmup_helpers import WarmupHelper, WarmupTeamEnrollment, WarmupSenderConfig
    from app.services.accounts_overview import build_overview
    from app.services.warmup_warmth import warmth_for_account
    from app.services import sender_eligibility as se
    from app.services.account_health import protection_snapshot
    from app.services.warmup_exclusion import enrollment_states_by_instance, mesh_role_for
    from sqlalchemy import select

    await engine.dispose()
    await _cleanup()
    NOW = datetime.utcnow()
    try:
        async with AsyncSessionLocal() as db:
            # 1) healthy eligible sender: old, clean, flagged warm peer, has a TC contact.
            healthy = _acct("healthy", 30, is_warm_peer=True)
            # 2) too-young peer being warmed (enrolled+enabled, 3 days old).
            young = _acct("young", 3)
            # 3) yellowCarded: old but a recent disqualifying incident + active cooldown.
            carded = _acct("carded", 30, incident_count_7d=1,
                           cooldown_until=NOW + timedelta(days=1))
            # 4) cold/recipient-only TC account (team-enrolled, no contacts of its own).
            cold = _acct("cold", 30)
            # 5) unassigned / no role at all (brand new).
            none_acct = _acct("none", 1)
            # 6) too-young but a logged eligibility override stands.
            override = _acct("override", 2)
            db.add_all([healthy, young, carded, cold, none_acct, override])
            await db.flush()

            db.add(WarmupEnrollment(instance_id=_iid("young"), state="RECEIVING", is_enabled=True,
                                    authorized_at=NOW - timedelta(days=3)))
            db.add(AccountIncident(account_id=carded.id, incident_type="yellowCard",
                                   severity="critical", detected_via="webhook",
                                   created_at=NOW - timedelta(days=2)))
            db.add(WarmupHelper(name="contact-1", phone="989120000001",
                                sender_instance_id=_iid("healthy"), is_active=True))
            db.add(WarmupTeamEnrollment(cold_instance_id=_iid("cold"), is_enabled=True,
                                        enrolled_at=NOW - timedelta(days=1)))
            db.add(WarmupSenderConfig(sender_instance_id=_iid("override"), is_enabled=True,
                                      eligibility_overridden_at=NOW - timedelta(hours=1),
                                      eligibility_override_note="approved for test",
                                      eligibility_overridden_by="admin"))
            await db.commit()

        async with AsyncSessionLocal() as db:
            rows = await build_overview(db, now=NOW)
            by_iid = {r["instance_id"]: r for r in rows}
            # every seeded account is present.
            for suffix in ("healthy", "young", "carded", "cold", "none", "override"):
                assert _iid(suffix) in by_iid, f"missing {suffix}"

            enr_map = await enrollment_states_by_instance(db)

            for suffix in ("healthy", "young", "carded", "cold", "none", "override"):
                iid = _iid(suffix)
                row = by_iid[iid]
                acct = (await db.execute(
                    select(Account).where(Account.instance_id == iid))).scalar_one()

                # ── warmth: exact shared evaluator ──
                w = await warmth_for_account(db, acct, NOW)
                assert row["warmth_score"] == w["score"], suffix
                assert row["warmth_level"] == w["level"], suffix
                assert row["warmth_components"] == w["components"], suffix
                assert row["days_connected"] == w["age_days"], suffix
                assert row["recent_incidents_14d"] == w["recent_incidents"], suffix
                assert row["incident_free_14d"] == (int(w["recent_incidents"] or 0) == 0), suffix

                # ── sender eligibility + override: exact TC functions ──
                elig, reason, msg, age = await se.check_sender_eligibility(db, iid, NOW)
                assert row["eligible"] == bool(elig), suffix
                assert row["eligibility_reason"] == reason, suffix
                assert row["eligibility_message"] == msg, suffix
                assert row["eligibility_override"] == bool(await se.has_valid_override(db, iid)), suffix

                # ── health / protection: exact shared snapshot ──
                snap = await protection_snapshot(acct, db)
                for k in ("health_score", "yellow_card_rate_7d", "reply_rate_7d",
                          "in_cooldown", "throttle_factor", "incident_count_7d"):
                    assert row[k] == snap[k], f"{suffix}:{k}"

                # ── mesh role: exact shared logic ──
                assert row["role"]["mesh"] == mesh_role_for(enr_map.get(iid), bool(acct.is_warm_peer)), suffix

                # ── incident summary: exact AccountIncident source ──
                incs = (await db.execute(
                    select(AccountIncident).where(AccountIncident.account_id == acct.id)
                    .order_by(AccountIncident.created_at.desc()))).scalars().all()
                assert row["incident_total"] == len(incs), suffix
                assert row["last_incident_type"] == (incs[0].incident_type if incs else None), suffix

            # ── spot-check the role SEMANTICS per combination ──
            assert by_iid[_iid("healthy")]["eligible"] is True
            assert by_iid[_iid("healthy")]["role"]["mesh"] == "peer_sender"
            assert by_iid[_iid("healthy")]["role"]["tc_sender"] is True
            assert by_iid[_iid("healthy")]["role"]["tc_contact_count"] == 1

            assert by_iid[_iid("young")]["role"]["mesh"] == "being_warmed"
            assert by_iid[_iid("young")]["eligible"] is False
            assert by_iid[_iid("young")]["eligibility_reason"] == "too_young"

            assert by_iid[_iid("carded")]["eligibility_reason"] == "recent_incident"
            assert by_iid[_iid("carded")]["in_cooldown"] is True
            assert by_iid[_iid("carded")]["health_score"] == 0.0
            assert by_iid[_iid("carded")]["last_incident_type"] == "yellowCard"
            assert by_iid[_iid("carded")]["incident_total"] == 1

            assert by_iid[_iid("cold")]["role"]["tc_cold"] is True
            assert by_iid[_iid("cold")]["role"]["tc_sender"] is False

            assert by_iid[_iid("none")]["role"]["none"] is True
            assert by_iid[_iid("none")]["role"]["mesh"] == "none"

            assert by_iid[_iid("override")]["eligibility_override"] is True
    finally:
        await _cleanup()
