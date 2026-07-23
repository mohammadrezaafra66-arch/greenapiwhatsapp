"""V41 Path B PART 1 — scheduled automatic recheck + auto-apply when both conditions clear.

Proves the automated wait-and-apply logic reuses the EXISTING rules and:
  • takes NO action (just logs a status) while the breaker is tripped and/or no peer qualifies;
  • auto-applies the recovery enrollment EXACTLY once, correctly, with the right peer, when BOTH
    conditions are met, and records the transition;
  • is idempotent — a second run after a successful enrollment is a safe no-op;
  • ABORTS the auto-apply (changes nothing) if any OTHER account's mesh enrollment was enabled;
  • NEVER resets the breaker and NEVER relaxes the peer bar (both must clear via the existing logic).
"""
import uuid
from datetime import datetime
from types import SimpleNamespace
import pytest

from app.services import warmup_recovery_autoenroll as ae
from app.services.warmup_recovery_autoenroll import run_recovery_autoenroll_check, RECHECK_EVENT
from app.services.warmup_state import WarmupState

NOW = datetime(2026, 7, 29, 1, 30, 0)
TARGET = "7105325764"


class _DB:
    """Minimal fake session: records added rows + commits; no queued execute results needed because
    every DB read this module does is routed through a monkeypatched helper in these unit tests."""
    def __init__(self):
        self.added = []
        self.commits = 0
    async def execute(self, q):  # pragma: no cover - not hit (helpers are patched)
        raise AssertionError("unexpected direct db.execute in unit test")
    def add(self, o): self.added.append(o)
    async def commit(self): self.commits += 1


def _patch(monkeypatch, *, breaker, peer_qualifies, peer_instance="AAA",
           target_enr=None, others=None):
    async def _load(db, target): return target_enr
    async def _breaker(db, now=None): return breaker
    async def _peer(db, target, now=None):
        peer = {"instance_id": peer_instance, "warmth_score": 80, "safe": True} if peer_qualifies else None
        return {"qualifies": peer_qualifies, "peer": peer, "candidates": []}
    async def _others(db): return others or {}
    monkeypatch.setattr(ae, "_load_target_enrollment", _load)
    monkeypatch.setattr(ae, "is_breaker_tripped", _breaker)
    monkeypatch.setattr(ae, "select_safe_peer", _peer)
    monkeypatch.setattr(ae, "enrollment_states_by_instance", _others)


def _recheck_rows(db):
    return [o for o in db.added if getattr(o, "event_type", None) == RECHECK_EVENT]


# ── blocked: breaker tripped ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_blocked_when_breaker_tripped(monkeypatch):
    applied = {"n": 0}
    async def _enroll(*a, **k): applied["n"] += 1; return {}
    monkeypatch.setattr(ae, "enroll_recovery_mode", _enroll)
    _patch(monkeypatch, breaker=True, peer_qualifies=True)
    res = await run_recovery_autoenroll_check(_DB(), NOW, TARGET)
    assert res["applied"] is False and res["blocked"] is True
    assert res["breaker_tripped"] is True
    assert applied["n"] == 0                       # never enrolled, breaker never reset
    assert "breaker=tripped" in res["message"]


# ── blocked: no eligible peer ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_blocked_when_no_peer(monkeypatch):
    applied = {"n": 0}
    async def _enroll(*a, **k): applied["n"] += 1; return {}
    monkeypatch.setattr(ae, "enroll_recovery_mode", _enroll)
    _patch(monkeypatch, breaker=False, peer_qualifies=False)
    db = _DB()
    res = await run_recovery_autoenroll_check(db, NOW, TARGET)
    assert res["applied"] is False and res["blocked"] is True
    assert res["peer_qualifies"] is False
    assert applied["n"] == 0
    assert "peer=none" in res["message"]
    # a durable status row is recorded so the history/dashboard can see the finding.
    assert len(_recheck_rows(db)) == 1 and db.commits == 1


# ── both clear → auto-apply exactly once, right peer, transition logged ───────
@pytest.mark.asyncio
async def test_auto_applies_when_both_clear(monkeypatch):
    calls = {"enroll": []}
    async def _enroll(db, target, now=None, *, commit=True):
        calls["enroll"].append((target, commit))
        return {"enrolled": True, "halted": False, "state": WarmupState.COOLDOWN.value,
                "day_index": 0, "recovery_mode": True, "is_enabled": True, "others_unchanged": True}
    monkeypatch.setattr(ae, "enroll_recovery_mode", _enroll)
    _patch(monkeypatch, breaker=False, peer_qualifies=True, peer_instance="770022683809")
    db = _DB()
    res = await run_recovery_autoenroll_check(db, NOW, TARGET)
    assert res["applied"] is True and res["action"] == "auto_applied"
    assert res["peer_instance"] == "770022683809"
    assert res["state"] == WarmupState.COOLDOWN.value and res["recovery_mode"] is True
    # existing enroller called exactly once, within the same (uncommitted) transaction.
    assert calls["enroll"] == [(TARGET, False)]
    assert len(_recheck_rows(db)) == 1 and db.commits == 1


# ── idempotent: already enrolled → safe no-op ────────────────────────────────
@pytest.mark.asyncio
async def test_idempotent_noop_when_already_enrolled(monkeypatch):
    calls = {"enroll": 0}
    async def _enroll(*a, **k): calls["enroll"] += 1; return {}
    monkeypatch.setattr(ae, "enroll_recovery_mode", _enroll)
    enr = SimpleNamespace(id=uuid.uuid4(), instance_id=TARGET, recovery_mode=True, is_enabled=True,
                          state=WarmupState.COOLDOWN.value)
    _patch(monkeypatch, breaker=False, peer_qualifies=True, target_enr=enr)
    db = _DB()
    res = await run_recovery_autoenroll_check(db, NOW, TARGET)
    assert res["applied"] is False and res["already_enrolled"] is True
    assert res["action"] == "noop_already_enrolled"
    assert calls["enroll"] == 0                     # never re-applies
    assert db.commits == 1


# ── guardrail: another account enabled → abort auto-apply, change nothing ─────
@pytest.mark.asyncio
async def test_aborts_when_other_account_enabled(monkeypatch):
    calls = {"enroll": 0}
    async def _enroll(*a, **k): calls["enroll"] += 1; return {}
    monkeypatch.setattr(ae, "enroll_recovery_mode", _enroll)
    # both conditions clear, BUT another account's enrollment is enabled → must abort.
    others = {TARGET: (WarmupState.PAUSED.value, False),
              "SOMEONE_ELSE": (WarmupState.RAMPING.value, True)}
    _patch(monkeypatch, breaker=False, peer_qualifies=True, others=others)
    db = _DB()
    res = await run_recovery_autoenroll_check(db, NOW, TARGET)
    assert res["applied"] is False and res.get("aborted_guardrail") is True
    assert res["other_enabled_instances"] == ["SOMEONE_ELSE"]
    assert calls["enroll"] == 0                     # auto-apply aborted — nothing enrolled
    assert db.commits == 1


# ── the existing enroller's own breaker guard still wins at apply time ────────
@pytest.mark.asyncio
async def test_respects_enroller_halt_if_breaker_flips(monkeypatch):
    async def _enroll(db, target, now=None, *, commit=True):
        return {"enrolled": False, "halted": True, "reason": "breaker_tripped"}
    monkeypatch.setattr(ae, "enroll_recovery_mode", _enroll)
    _patch(monkeypatch, breaker=False, peer_qualifies=True)
    res = await run_recovery_autoenroll_check(_DB(), NOW, TARGET)
    assert res["applied"] is False and res["blocked"] is True
    assert res["action"] == "blocked_on_apply"
