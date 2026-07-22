"""V41 PART 4 — enroll into mesh recovery mode + peer selection, with the two hard stops.

Proves:
  • enroll_recovery_mode sets is_enabled=true / COOLDOWN / day_index=0 / recovery_mode=true and
    leaves every OTHER enrollment's is_enabled unchanged;
  • the breaker-tripped case HALTS and reports (never enrolls, never silently resets the breaker);
  • peer selection reuses the EXISTING eligibility + warmth logic and reports the safest pick, or an
    accurate "none qualify" finding when nothing passes the existing bar (never picks an ineligible).
"""
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

from app.services import warmup_recovery_enroll as re
from app.services.warmup_recovery_enroll import (
    enroll_recovery_mode, select_safe_peer, rank_peer_candidates, RECOVERY_TARGET_INSTANCE,
)
from app.services.warmup_state import WarmupState

NOW = datetime(2026, 7, 22, 12, 0, 0)


# ── fake session (ordered results queue) ─────────────────────────────────────
class _Scalars:
    def __init__(self, items): self._items = list(items)
    def all(self): return list(self._items)


class _Res:
    def __init__(self, scalars=None):
        self._s = scalars if scalars is not None else []
    def scalars(self): return _Scalars(self._s)
    def scalar_one_or_none(self): return self._s[0] if self._s else None


class _DB:
    def __init__(self, results=None):
        self._results = list(results or [])
        self.added = []
        self.commits = 0
        self.flushes = 0
    async def execute(self, q): return self._results.pop(0) if self._results else _Res()
    def add(self, o): self.added.append(o)
    async def flush(self): self.flushes += 1
    async def commit(self): self.commits += 1


def _acc(iid, **kw):
    base = dict(id=uuid.uuid4(), instance_id=iid, name=f"acct-{iid}", phone=iid,
                status=None)
    base.update(kw)
    return SimpleNamespace(**base)


# ── enrollment fields + others-unchanged ─────────────────────────────────────
@pytest.mark.asyncio
async def test_enroll_sets_recovery_fields(monkeypatch):
    async def _no_breaker(db, now=None): return False
    async def _others(db): return {"AAA": (WarmupState.PAUSED.value, False),
                                   "BBB": (WarmupState.GRADUATED.value, False)}
    monkeypatch.setattr(re, "is_breaker_tripped", _no_breaker)
    monkeypatch.setattr(re, "enrollment_states_by_instance",
                        lambda db: _wrap({"7105325764": (WarmupState.PAUSED.value, False),
                                          "AAA": (WarmupState.PAUSED.value, False),
                                          "BBB": (WarmupState.GRADUATED.value, False)}))
    # enrollment query → none (create); account query → the account
    db = _DB(results=[_Res(scalars=[]), _Res(scalars=[_acc("7105325764")])])
    res = await enroll_recovery_mode(db, "7105325764", NOW)
    assert res["enrolled"] is True and res["halted"] is False
    assert res["state"] == WarmupState.COOLDOWN.value
    assert res["day_index"] == 0
    assert res["recovery_mode"] is True
    assert res["is_enabled"] is True
    assert res["created"] is True
    # every OTHER enrollment stayed disabled (guardrail 2).
    assert res["others_unchanged"] is True
    assert res["other_enabled_instances"] == []
    # the created enrollment object carries the right fields.
    enr = next(o for o in db.added if getattr(o, "instance_id", None) == "7105325764"
               and hasattr(o, "recovery_mode"))
    assert enr.recovery_mode is True and enr.state == WarmupState.COOLDOWN.value
    assert enr.is_enabled is True and enr.day_index == 0
    assert enr.next_action_at == NOW + timedelta(hours=24)   # 24h cooldown anchor
    assert db.commits == 1


def _wrap(d):
    async def _coro(*_a, **_k):
        return d
    return _coro()


# ── HARD STOP 1: breaker tripped ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_enroll_halts_when_breaker_tripped(monkeypatch):
    async def _tripped(db, now=None): return True
    monkeypatch.setattr(re, "is_breaker_tripped", _tripped)
    db = _DB()
    res = await enroll_recovery_mode(db, "7105325764", NOW)
    assert res["halted"] is True and res["enrolled"] is False
    assert res["reason"] == "breaker_tripped"
    # Nothing written, nothing committed — the breaker is NOT silently reset.
    assert db.added == [] and db.commits == 0


# ── peer selection reuses existing eligibility + warmth ──────────────────────
def _patch_peer_logic(monkeypatch, pool, elig_by, warmth_by, healthy_by):
    async def _pool(db, exclude): return pool
    async def _elig(db, acc, now=None): return elig_by[acc.instance_id]
    async def _warmth(db, acc, now=None): return warmth_by[acc.instance_id]
    def _healthy(acc, now=None): return healthy_by[acc.instance_id]
    monkeypatch.setattr(re, "eligible_peer_accounts", _pool)
    monkeypatch.setattr(re, "check_peer_eligibility", _elig)
    monkeypatch.setattr(re, "warmth_for_account", _warmth)
    monkeypatch.setattr(re, "is_peer_healthy", _healthy)


@pytest.mark.asyncio
async def test_select_safe_peer_picks_safest(monkeypatch):
    a, b, c = _acc("A"), _acc("B"), _acc("C")
    _patch_peer_logic(
        monkeypatch, [a, b, c],
        elig_by={"A": (True, "ok", None), "B": (True, "ok", None), "C": (False, "too_young", "x")},
        warmth_by={"A": {"score": 72, "level": "بالا", "age_days": 20},
                   "B": {"score": 88, "level": "بالا", "age_days": 30},
                   "C": {"score": 10, "level": "کم", "age_days": 1}},
        healthy_by={"A": True, "B": True, "C": True})
    res = await select_safe_peer(_DB(), "7105325764", NOW)
    assert res["qualifies"] is True
    # B is eligible+healthy with the highest warmth → safest.
    assert res["peer"]["instance_id"] == "B"
    # C (ineligible) is ranked last and never chosen.
    assert res["candidates"][-1]["instance_id"] == "C"
    assert res["candidates"][-1]["safe"] is False


@pytest.mark.asyncio
async def test_select_safe_peer_none_qualify(monkeypatch):
    # An eligible-but-UNHEALTHY peer and a too-young peer → nothing is safe → report, don't pick.
    a, b = _acc("A"), _acc("B")
    _patch_peer_logic(
        monkeypatch, [a, b],
        elig_by={"A": (True, "ok", None), "B": (False, "too_young", "x")},
        warmth_by={"A": {"score": 80, "level": "بالا", "age_days": 30},
                   "B": {"score": 20, "level": "کم", "age_days": 2}},
        healthy_by={"A": False, "B": True})   # A eligible but resting/throttled → not usable now
    res = await select_safe_peer(_DB(), "7105325764", NOW)
    assert res["qualifies"] is False
    assert res["peer"] is None
    assert {c["instance_id"] for c in res["candidates"]} == {"A", "B"}


@pytest.mark.asyncio
async def test_select_safe_peer_empty_pool(monkeypatch):
    _patch_peer_logic(monkeypatch, [], elig_by={}, warmth_by={}, healthy_by={})
    res = await select_safe_peer(_DB(), "7105325764", NOW)
    assert res["qualifies"] is False and res["peer"] is None and res["candidates"] == []


def test_target_constant():
    assert RECOVERY_TARGET_INSTANCE == "7105325764"
