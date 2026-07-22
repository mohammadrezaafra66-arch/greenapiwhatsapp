"""V39 PART 3 — send-time defense-in-depth for the Team-Collaboration sender-eligibility gate.

Proves that `_send_as_sender` (the guard now wrapping every TC sender send — ask / reminder /
thank-you) blocks a sender that BYPASSED PART 2's assignment-time check:
  • a legacy / directly-DB-edited sender that is ineligible (<14 days, or a recent incident) and has
    NO logged override is BLOCKED at send time — no Green API call;
  • an ELIGIBLE sender, or one carrying a VALID logged override, sends normally;
  • a lookup error fails OPEN (never breaks the tick), and a None sender is allowed;
  • scoping: the four sender-role sites route through the guard, while the cold-reply path (a young
    cold account answering) intentionally does NOT (it would otherwise be wrongly blocked).
"""
import uuid
import inspect
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.services import warmup_helper_engine as he
from app.services import send_gate
from app.services import sender_eligibility as se
from app.models.warmup_mesh import WarmupEnrollment
from app.models.warmup_helpers import WarmupSenderConfig

NOW = datetime(2026, 7, 22, 12, 0, 0)

# The REAL guard implementation, captured before conftest's autouse fixture stubs it to always-allow.
_REAL_SENDER_SEND_ALLOWED = se.sender_send_allowed


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    send_gate.clear_live_cache()
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    # Undo conftest's suite-wide "allow" stub so THIS file exercises the real eligibility decision.
    monkeypatch.setattr("app.services.sender_eligibility.sender_send_allowed",
                        _REAL_SENDER_SEND_ALLOWED)
    yield
    send_gate.clear_live_cache()


# ── fake session (SQL-string routing) ────────────────────────────────────────
class _Res:
    def __init__(self, scalars=None, scalar=None):
        self._s = scalars or []
        self._scalar = scalar
    def scalars(self):
        outer = self
        class _S:
            def all(s): return list(outer._s)
        return _S()
    def scalar(self): return self._scalar
    def scalar_one_or_none(self): return self._s[0] if self._s else None


class _DB:
    def __init__(self, account=None, enr=None, incident_count=0, cfg=None, raise_on_execute=False):
        self.account, self.enr, self.incident_count, self.cfg = account, enr, incident_count, cfg
        self.raise_on_execute = raise_on_execute
        self.added = []
    async def execute(self, q):
        if self.raise_on_execute:
            raise RuntimeError("db hiccup")
        sql = str(q).lower()
        if "count(" in sql:
            return _Res(scalar=self.incident_count)
        if "warmup_enrollment" in sql:
            return _Res(scalars=[self.enr] if self.enr else [])
        if "warmup_sender_config" in sql:
            return _Res(scalars=[self.cfg] if self.cfg else [])
        if "accounts" in sql:
            return _Res(scalars=[self.account] if self.account else [])
        return _Res()
    def add(self, x): self.added.append(x)
    async def flush(self): pass
    async def commit(self): pass


def _acc(iid="S1"):
    return SimpleNamespace(instance_id=iid, name="فرستنده", id=uuid.uuid4(),
                           partner_created_at=None, created_at=None)


def _enr(days_old):
    return WarmupEnrollment(instance_id="S1", authorized_at=NOW - timedelta(days=days_old),
                            last_activity_at=NOW - timedelta(days=1))


def _sender(iid="S1"):
    # grandfathered (connected_at None) + active, so _send_from_main's connect-cooldown / health
    # gate does not itself block — isolating the PART 3 eligibility decision.
    return SimpleNamespace(instance_id=iid, api_token="t", name="فرستنده", phone="9890",
                           status=SimpleNamespace(value="active"),
                           connected_at=None, reconnected_at=None,
                           cooldown_until=None, throttle_until=None, throttle_factor=1.0)


def _factory(counter):
    def factory(iid, tok):
        c = MagicMock()
        c.send_typing_ms = AsyncMock(return_value=True)
        async def _s(p, t):
            counter["n"] += 1
            return "MID"
        c.send_message = AsyncMock(side_effect=_s)
        return c
    return factory


# ── the guard ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_legacy_ineligible_sender_blocked_at_send_time():
    """A sender that bypassed PART 2 (ineligible, no override) is blocked — no Green API call."""
    db = _DB(account=_acc(), enr=_enr(6.9), incident_count=0, cfg=None)
    calls = {"n": 0}
    mid = await he._send_as_sender(db, _sender(), "989120000001", "سلام", _factory(calls), NOW)
    assert mid is None and calls["n"] == 0


@pytest.mark.asyncio
async def test_recent_incident_sender_blocked_at_send_time():
    db = _DB(account=_acc(), enr=_enr(20), incident_count=1, cfg=None)
    calls = {"n": 0}
    mid = await he._send_as_sender(db, _sender(), "989120000001", "سلام", _factory(calls), NOW)
    assert mid is None and calls["n"] == 0


@pytest.mark.asyncio
async def test_eligible_sender_sends():
    db = _DB(account=_acc(), enr=_enr(20), incident_count=0, cfg=None)
    calls = {"n": 0}
    mid = await he._send_as_sender(db, _sender(), "989120000002", "سلام", _factory(calls), NOW)
    assert mid == "MID" and calls["n"] == 1


@pytest.mark.asyncio
async def test_overridden_sender_sends():
    cfg = WarmupSenderConfig(sender_instance_id="S1", is_enabled=True,
                             eligibility_overridden_at=NOW - timedelta(days=1),
                             eligibility_override_note="ریسک پذیرفته شد", eligibility_overridden_by="admin")
    db = _DB(account=_acc(), enr=_enr(6.9), incident_count=0, cfg=cfg)   # ineligible BUT overridden
    calls = {"n": 0}
    mid = await he._send_as_sender(db, _sender(), "989120000003", "سلام", _factory(calls), NOW)
    assert mid == "MID" and calls["n"] == 1


@pytest.mark.asyncio
async def test_lookup_error_fails_open():
    db = _DB(raise_on_execute=True)
    calls = {"n": 0}
    mid = await he._send_as_sender(db, _sender(), "989120000004", "سلام", _factory(calls), NOW)
    assert mid == "MID" and calls["n"] == 1


@pytest.mark.asyncio
async def test_none_sender_id_allowed():
    db = _DB()
    calls = {"n": 0}
    s = _sender(iid=None)
    mid = await he._send_as_sender(db, s, "989120000005", "سلام", _factory(calls), NOW)
    assert mid == "MID" and calls["n"] == 1


# ── scoping: sender-role paths guarded, cold-reply path NOT ──────────────────
def test_sender_role_sites_use_guard_cold_reply_does_not():
    from app.services import warmup_team_schedule, warmup_thankyou, warmup_cold_reply
    assert "_send_as_sender(db, sender" in inspect.getsource(warmup_team_schedule)
    assert "_send_as_sender(db, sender" in inspect.getsource(warmup_thankyou)
    # ask/reminder + thank-you in the engine go through the guard
    eng = inspect.getsource(he)
    assert eng.count("_send_as_sender(") >= 3
    # the cold-reply path must NOT gate the (young) cold account on sender-eligibility
    assert "_send_as_sender" not in inspect.getsource(warmup_cold_reply)
