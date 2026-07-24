"""V48 PART 4 — end-to-end: the unified overview matches what the FOUR existing PAGES show.

Where PART 2 cross-checks the overview against the shared source FUNCTIONS, PART 4 cross-checks it
against the actual PAGE ENDPOINT handlers (`/accounts/`, `/incidents/protection`,
`/warmup-helpers/warmth`, `/warmup-helpers/sender-eligibility`, `/warmup/mesh-dashboard`) — the exact
payloads the four detail pages render — for a realistic mixed roster modeled on the real live
accounts (a recently-yellowCarded primary, a group of too-young cold/team-enrolled numbers, and a
brand-new role-less number).
"""
import uuid
from datetime import datetime, timedelta

import pytest

PREFIX = "V48E2E-"


def _iid(s):
    return f"{PREFIX}{s}"


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


def _acct(suffix, days_ago, **kw):
    from app.models.account import Account, AccountStatus
    base = dict(
        id=uuid.uuid4(), name=f"acct-{suffix}", instance_id=_iid(suffix), api_token="tok",
        status=AccountStatus.active, phone="9891" + suffix.replace("-", "")[:7].ljust(7, "0"),
        sent_today=3, received_today=5, is_warm_peer=False, incident_count_7d=0,
        created_at=datetime.utcnow() - timedelta(days=days_ago),
    )
    base.update(kw)
    return Account(**base)


@pytest.mark.asyncio
async def test_overview_matches_the_four_pages_for_a_live_like_roster(monkeypatch):
    from app.database import AsyncSessionLocal, engine
    from app.models.incident import AccountIncident
    from app.models.warmup_mesh import WarmupEnrollment
    from app.models.warmup_helpers import WarmupTeamEnrollment
    from app.api.v1.accounts import accounts_overview
    from app.api.v1.incidents import protection as protection_ep
    from app.api.v1.warmup import mesh_dashboard
    from app.api.v1.warmup_helpers import warmth as warmth_ep, sender_eligibility_check

    await engine.dispose()
    await _cleanup()
    NOW = datetime.utcnow()
    try:
        async with AsyncSessionLocal() as db:
            # primary: old, but a fresh yellowCard 2 days ago (like 7105325764).
            primary = _acct("primary", 21, incident_count_7d=1)
            # cold group: ~9 days old, paused mesh enrollment + team-enrolled (like 683809/810/838).
            cold1 = _acct("cold1", 9)
            cold2 = _acct("cold2", 9)
            # brand-new, no role at all.
            fresh = _acct("fresh", 2)
            db.add_all([primary, cold1, cold2, fresh])
            await db.flush()
            db.add(AccountIncident(account_id=primary.id, incident_type="yellowCard",
                                   severity="critical", detected_via="webhook",
                                   created_at=NOW - timedelta(days=2)))
            for c in (cold1, cold2):
                db.add(WarmupEnrollment(instance_id=c.instance_id, state="PAUSED", is_enabled=False,
                                        authorized_at=NOW - timedelta(days=9)))
                db.add(WarmupTeamEnrollment(cold_instance_id=c.instance_id, is_enabled=True,
                                            enrolled_at=NOW - timedelta(days=8)))
            await db.commit()

        async with AsyncSessionLocal() as db:
            ov = {r["instance_id"]: r for r in (await accounts_overview(db))["accounts"]}
            prot = {p["account_id"]: p for p in (await protection_ep(db))["accounts"]}
            warmth = {w["instance_id"]: w for w in (await warmth_ep(db))["senders"]}
            mesh_roles = {r["instance_id"]: r for r in (await mesh_dashboard(db))["roles"]}

            for suffix in ("primary", "cold1", "cold2", "fresh"):
                iid = _iid(suffix)
                row = ov[iid]
                aid = row["account_id"]

                # ── vs /warmup-helpers/warmth (the warmth badge on /warmup + /team-collaboration) ──
                w = warmth[iid]
                assert row["warmth_score"] == w["score"], suffix
                assert row["warmth_level"] == w["level"], suffix
                assert row["days_connected"] == w["age_days"], suffix
                assert row["recent_incidents_14d"] == w["recent_incidents"], suffix

                # ── vs /warmup-helpers/sender-eligibility (the TC eligibility dialog) ──
                se = await sender_eligibility_check(iid, db)
                assert row["eligible"] == se["eligible"], suffix
                assert row["eligibility_reason"] == se["reason"], suffix

                # ── vs /incidents/protection (the health page) ──
                p = prot[aid]
                for k in ("health_score", "yellow_card_rate_7d", "reply_rate_7d",
                          "in_cooldown", "incident_count_7d"):
                    assert row[k] == p[k], f"{suffix}:{k}"
                assert row["status"] == p["status"], suffix

                # ── vs /warmup/mesh-dashboard (the mesh role overview) ──
                assert row["role"]["mesh"] == mesh_roles[iid]["role"], suffix

            # ── semantics mirror the real live situation ──
            assert ov[_iid("primary")]["eligibility_reason"] == "recent_incident"
            assert ov[_iid("primary")]["last_incident_type"] == "yellowCard"
            assert ov[_iid("primary")]["role"]["mesh"] == "none"
            for c in ("cold1", "cold2"):
                assert ov[_iid(c)]["eligibility_reason"] == "too_young"
                assert ov[_iid(c)]["role"]["tc_cold"] is True
                assert ov[_iid(c)]["role"]["mesh"] == "none"   # paused enrollment → not being warmed
            assert ov[_iid("fresh")]["role"]["none"] is True
    finally:
        await _cleanup()
