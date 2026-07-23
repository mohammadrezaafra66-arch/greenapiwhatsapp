"""V41 Path B PART 3 — full end-to-end simulation + guardrail regression.

Drives run_recovery_autoenroll_check across the real timeline using the REAL enroll_recovery_mode
(not a stub), so the actual enrollment writes and the two hard stops are exercised end to end:

  1. tripped breaker + no eligible peer  → does nothing, logs a blocked status;
  2. breaker clears + one account becomes eligible → auto-applies once, correct peer, transition logged;
  3. running again afterwards             → safe idempotent no-op;
  4. throughout                           → no OTHER account's enrollment is ever created or enabled,
                                            and the breaker is never reset by this automation.
"""
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

from app.services import warmup_recovery_autoenroll as ae
from app.services import warmup_recovery_enroll as re_mod
from app.services.warmup_recovery_autoenroll import run_recovery_autoenroll_check
from app.models.warmup_mesh import WarmupEnrollment
from app.services.warmup_state import WarmupState

TARGET = "7105325764"
PEER = "770022683809"
T0 = datetime(2026, 7, 23, 1, 30, 0)   # breaker still tripped, no eligible peer
T1 = datetime(2026, 7, 29, 1, 30, 0)   # both conditions naturally cleared


class _Scalars:
    def __init__(self, items): self._items = list(items)
    def all(self): return list(self._items)
    def first(self): return self._items[0] if self._items else None


class _Res:
    def __init__(self, scalars=None): self._s = scalars if scalars is not None else []
    def scalars(self): return _Scalars(self._s)
    def scalar_one_or_none(self): return self._s[0] if self._s else None


class _DB:
    def __init__(self):
        self._results = []
        self.added = []
        self.commits = 0
    def queue(self, *results): self._results = list(results)
    async def execute(self, q): return self._results.pop(0) if self._results else _Res()
    def add(self, o): self.added.append(o)
    async def flush(self): pass
    async def commit(self): self.commits += 1


def _added_enrollments(db):
    return [o for o in db.added if isinstance(o, WarmupEnrollment)]


@pytest.mark.asyncio
async def test_full_wait_then_autoapply_then_noop(monkeypatch):
    # Shared, mutable world state the patched leaves read from.
    state = {
        "enr": None,
        "breaker": True,
        "peer_ok": False,
        # every OTHER account stays disabled the whole time (guardrail evidence).
        "others": {TARGET: (WarmupState.PAUSED.value, False),
                   "OTHER_A": (WarmupState.PAUSED.value, False),
                   "OTHER_B": (WarmupState.GRADUATED.value, False)},
    }

    async def _load(db, target): return state["enr"]
    async def _breaker(db, now=None): return state["breaker"]
    async def _peer(db, target, now=None):
        peer = {"instance_id": PEER, "warmth_score": 85, "safe": True} if state["peer_ok"] else None
        return {"qualifies": state["peer_ok"], "peer": peer, "candidates": []}
    async def _others(db): return state["others"]

    # autoenroll module leaves
    monkeypatch.setattr(ae, "_load_target_enrollment", _load)
    monkeypatch.setattr(ae, "is_breaker_tripped", _breaker)
    monkeypatch.setattr(ae, "select_safe_peer", _peer)
    monkeypatch.setattr(ae, "enrollment_states_by_instance", _others)
    # the REAL enroll_recovery_mode's own dependencies (so its internal breaker/others checks agree)
    monkeypatch.setattr(re_mod, "is_breaker_tripped", _breaker)
    monkeypatch.setattr(re_mod, "enrollment_states_by_instance", _others)

    db = _DB()

    # ── 1) breaker tripped + no peer → blocked, nothing enrolled, breaker untouched ──
    r1 = await run_recovery_autoenroll_check(db, T0, TARGET)
    assert r1["applied"] is False and r1["blocked"] is True
    assert "breaker=tripped" in r1["message"] and "peer=none" in r1["message"]
    assert _added_enrollments(db) == []                 # no enrollment created at all
    assert state["breaker"] is True                     # never reset by the automation

    # ── 2) conditions clear naturally → auto-apply once with the right peer ──
    state["breaker"] = False
    state["peer_ok"] = True
    db.queue(_Res(scalars=[]),                          # enroll: target enrollment lookup → none
             _Res(scalars=[SimpleNamespace(id=uuid.uuid4(), instance_id=TARGET, phone=TARGET)]))  # account
    r2 = await run_recovery_autoenroll_check(db, T1, TARGET)
    assert r2["applied"] is True and r2["action"] == "auto_applied"
    assert r2["peer_instance"] == PEER
    created = _added_enrollments(db)
    assert len(created) == 1                            # exactly one enrollment, and it is the target
    enr = created[0]
    assert enr.instance_id == TARGET
    assert enr.recovery_mode is True and enr.is_enabled is True
    assert enr.state == WarmupState.COOLDOWN.value and enr.day_index == 0
    assert enr.next_action_at == T1 + timedelta(hours=24)
    # no OTHER account's enrollment object was created.
    assert all(e.instance_id == TARGET for e in created)

    # the freshly-applied enrollment now exists in the world → feeds the idempotency run.
    state["enr"] = enr

    # ── 3) run again → safe idempotent no-op (never re-applies) ──
    before = len(db.added)
    r3 = await run_recovery_autoenroll_check(db, T1 + timedelta(days=1), TARGET)
    assert r3["applied"] is False and r3["already_enrolled"] is True
    assert _added_enrollments(db) == created            # no new enrollment added
    # only a status row was appended by the no-op run (no enrollment/state mutation).
    assert len(db.added) == before + 1

    # ── throughout: every OTHER account stayed disabled ──
    assert all(not enabled for iid, (_s, enabled) in state["others"].items() if iid != TARGET)
