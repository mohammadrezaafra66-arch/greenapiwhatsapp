"""V41 PART 3 — Team Collaboration sender pause + a DISTINCT «in mesh recovery» indicator.

Proves:
  • while an account is mid mesh-recovery re-warm it is INELIGIBLE as a TC sender, with a distinct
    reason slug `in_mesh_recovery` (not a generic too-young / recent-incident), taking precedence;
  • the send-time guard HARD-blocks a recovery sender even when a deliberate eligibility override
    stands — sending during recovery is exactly what re-triggers a ban;
  • a GRADUATED recovery enrollment is no longer «in recovery» → eligible again on normal terms;
  • the existing V39 override behavior for a plain ineligible (non-recovery) sender is unchanged.
"""
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

from app.services import sender_eligibility as se
from app.services.sender_eligibility import (
    enrollment_in_mesh_recovery, check_sender_eligibility, sender_send_allowed, override_active,
)
from app.services.warmup_state import WarmupState
from app.services.warmup_peer_eligibility import MIN_PEER_AGE_DAYS

NOW = datetime(2026, 7, 22, 12, 0, 0)

# Restore the REAL send-time guard (conftest stubs it to always-allow for orthogonal tick tests).
_REAL_SENDER_SEND_ALLOWED = se.sender_send_allowed


@pytest.fixture(autouse=True)
def _use_real_guard(monkeypatch):
    monkeypatch.setattr("app.services.sender_eligibility.sender_send_allowed",
                        _REAL_SENDER_SEND_ALLOWED)
    yield


# ── ordered-queue fake session (account → enrollment → [incident/config]) ─────
class _Scalars:
    def __init__(self, items): self._items = list(items)
    def all(self): return list(self._items)


class _Res:
    def __init__(self, scalars=None, scalar=None):
        self._s = scalars if scalars is not None else []
        self._scalar = scalar
    def scalars(self): return _Scalars(self._s)
    def scalar_one_or_none(self): return self._s[0] if self._s else None
    def scalar(self): return self._scalar


class _DB:
    def __init__(self, results):
        self._results = list(results)
        self.added = []
    async def execute(self, q):
        return self._results.pop(0) if self._results else _Res()
    def add(self, obj): self.added.append(obj)
    async def commit(self): pass


def _acc(iid="7105325764"):
    return SimpleNamespace(id=uuid.uuid4(), instance_id=iid, name="9122270261",
                           phone="9122270261", partner_created_at=NOW - timedelta(days=30),
                           created_at=NOW - timedelta(days=30))


def _enr(state=WarmupState.RECEIVING.value, recovery=True, enabled=True):
    return SimpleNamespace(instance_id="7105325764", state=state,
                           recovery_mode=recovery, is_enabled=enabled,
                           authorized_at=NOW - timedelta(days=2))


# ── pure predicate ───────────────────────────────────────────────────────────
def test_enrollment_in_mesh_recovery_predicate():
    assert enrollment_in_mesh_recovery(_enr()) is True
    assert enrollment_in_mesh_recovery(_enr(recovery=False)) is False
    assert enrollment_in_mesh_recovery(_enr(enabled=False)) is False
    # GRADUATED = done recovering → not «in recovery» anymore.
    assert enrollment_in_mesh_recovery(_enr(state=WarmupState.GRADUATED.value)) is False
    assert enrollment_in_mesh_recovery(None) is False


# ── eligibility reason is distinct and takes precedence ──────────────────────
@pytest.mark.asyncio
async def test_recovery_sender_ineligible_with_distinct_reason():
    db = _DB([_Res(scalars=[_acc()]), _Res(scalars=[_enr()])])
    eligible, reason, msg, age = await check_sender_eligibility(db, "7105325764", NOW)
    assert eligible is False
    assert reason == "in_mesh_recovery"          # DISTINCT from too_young / recent_incident
    assert "بازیابی" in msg                      # Persian «recovery» wording
    assert age is not None                        # age still reported for context


@pytest.mark.asyncio
async def test_recovery_precedes_recent_incident_reason():
    # Even a young account (would be too_young) reports the recovery reason first — it is the
    # SPECIFIC reason it is paused. (No incident-count query is reached; recovery short-circuits.)
    young_acc = SimpleNamespace(id=uuid.uuid4(), instance_id="7105325764", name="x", phone="x",
                                partner_created_at=NOW - timedelta(days=1),
                                created_at=NOW - timedelta(days=1))
    db = _DB([_Res(scalars=[young_acc]), _Res(scalars=[_enr()])])
    eligible, reason, _msg, _age = await check_sender_eligibility(db, "7105325764", NOW)
    assert (eligible, reason) == (False, "in_mesh_recovery")


# ── send-time HARD block, unoverridable ──────────────────────────────────────
@pytest.mark.asyncio
async def test_recovery_send_hard_blocked_even_with_override():
    # A standing override exists (proves override IS present)…
    cfg = SimpleNamespace(sender_instance_id="7105325764", eligibility_overridden_at=NOW)
    assert override_active(cfg) is True
    # …yet the send-time guard still refuses, because recovery short-circuits before the override
    # check (queue: account, enrollment — the config query is never even reached).
    db = _DB([_Res(scalars=[_acc()]), _Res(scalars=[_enr()])])
    allowed, reason = await sender_send_allowed(db, "7105325764", NOW)
    assert allowed is False
    assert reason == "in_mesh_recovery"


@pytest.mark.asyncio
async def test_graduated_recovery_sender_eligible_again():
    # After graduation the recovery pause lifts; a 30-day clean account is eligible normally.
    db = _DB([_Res(scalars=[_acc()]),
              _Res(scalars=[_enr(state=WarmupState.GRADUATED.value)]),
              _Res(scalar=0)])   # recent incident count
    eligible, reason, _msg, _age = await check_sender_eligibility(db, "7105325764", NOW)
    assert eligible is True and reason == "ok"


# ── in_mesh_recovery_ids collector ───────────────────────────────────────────
@pytest.mark.asyncio
async def test_in_mesh_recovery_ids():
    e1 = _enr(); e1.instance_id = "A"
    e2 = _enr(recovery=False); e2.instance_id = "B"
    e3 = _enr(state=WarmupState.GRADUATED.value); e3.instance_id = "C"
    db = _DB([_Res(scalars=[e1, e2, e3])])
    ids = await se.in_mesh_recovery_ids(db)
    assert ids == {"A"}


# ── regression: plain (non-recovery) override behavior unchanged ─────────────
@pytest.mark.asyncio
async def test_non_recovery_override_still_allows_send():
    # A too-young, non-recovery sender WITH a standing override sends (existing V39 behavior).
    young_acc = SimpleNamespace(id=uuid.uuid4(), instance_id="OTHER", name="x", phone="x",
                                partner_created_at=NOW - timedelta(days=1),
                                created_at=NOW - timedelta(days=1))
    enr = SimpleNamespace(instance_id="OTHER", state=WarmupState.COOLDOWN.value,
                          recovery_mode=False, is_enabled=True,
                          authorized_at=NOW - timedelta(days=1))
    cfg = SimpleNamespace(sender_instance_id="OTHER", eligibility_overridden_at=NOW)
    # queue: account, enrollment, incident-count (young→too_young), then config for has_valid_override
    db = _DB([_Res(scalars=[young_acc]), _Res(scalars=[enr]), _Res(scalar=0),
              _Res(scalars=[cfg])])
    allowed, reason = await sender_send_allowed(db, "OTHER", NOW)
    assert allowed is True and reason == "overridden"
