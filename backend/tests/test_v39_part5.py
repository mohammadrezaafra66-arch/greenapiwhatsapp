"""V39 PART 5 — final wiring + full end-to-end regression of the two guardrails.

End-to-end lifecycle of a brand-new account:
  1. it connects → the universal 24h connect-cooldown blocks it on EVERY path (mesh/campaign/TC);
  2. 24h later → the cooldown clears, so GENERAL sending (mesh/campaign) is allowed, but the account
     is still <14 days old, so the Team-Collaboration SENDER role stays blocked (send-time gate);
  3. an explicit, note-backed override is recorded (persisted + audit-logged) → the sender may now
     send; the send proceeds.
Plus wiring assertions: every send path consults the shared gate (connect-cooldown), the four TC
sender-role sites route through the eligibility guard, and grandfathered (NULL-anchor) accounts are
never blocked.
"""
import uuid
import inspect
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.services import send_gate
from app.services import sender_eligibility as se
from app.services import warmup_helper_engine as he
from app.services.send_gate import can_send_now
from app.models.warmup_mesh import WarmupEnrollment
from app.models.warmup_helpers import WarmupSenderConfig, WarmupHelperLog

NOW = datetime(2026, 7, 22, 12, 0, 0)
_REAL_SENDER_SEND_ALLOWED = se.sender_send_allowed


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    send_gate.clear_live_cache()
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    monkeypatch.setattr("app.services.sender_eligibility.sender_send_allowed",
                        _REAL_SENDER_SEND_ALLOWED)   # undo conftest's suite-wide allow-stub
    yield
    send_gate.clear_live_cache()


# ── fake session ─────────────────────────────────────────────────────────────
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
    def __init__(self, account=None, enr=None, incident_count=0, cfg=None):
        self.account, self.enr, self.incident_count, self.cfg = account, enr, incident_count, cfg
        self.added = []
    async def execute(self, q):
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
    def add(self, x):
        self.added.append(x)
        if isinstance(x, WarmupSenderConfig):
            self.cfg = x
    async def flush(self): pass
    async def commit(self): pass


def _acc(iid="NEW", connected_at=None):
    return SimpleNamespace(instance_id=iid, api_token="t", name="اکانت نو", id=uuid.uuid4(),
                           phone="9890", status=SimpleNamespace(value="active"),
                           connected_at=connected_at, reconnected_at=None,
                           partner_created_at=None, created_at=connected_at,
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


# ── the end-to-end lifecycle ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_new_account_lifecycle_cooldown_then_sender_gate_then_override():
    acct = _acc("NEW", connected_at=NOW)                       # brand-new: just connected
    enr = WarmupEnrollment(instance_id="NEW", authorized_at=NOW, last_activity_at=NOW)

    # 1) within 24h → connect-cooldown blocks EVERY path (the gate is shared by mesh/campaign/TC).
    assert can_send_now(acct, live_state="authorized", now=NOW) == (False, "connect_cooldown")

    # 2) at +25h → cooldown cleared → general sending allowed…
    later = NOW + timedelta(hours=25)
    assert can_send_now(acct, live_state="authorized", now=later) == (True, "ok")
    # …but the TC SENDER role is still blocked: the account is only ~1 day old (<14), no override.
    db = _DB(account=_acc("NEW", connected_at=NOW), enr=enr, incident_count=0, cfg=None)
    allowed, reason = await se.sender_send_allowed(db, "NEW", later)
    assert allowed is False and reason == "too_young"
    # the send-time guard blocks the actual send — no Green API call. (The send-object is
    # grandfathered so _send_from_main's own real-time connect-cooldown never confounds the test;
    # the eligibility decision comes from the DB via `later`.)
    calls = {"n": 0}
    mid = await he._send_as_sender(db, _acc("NEW", connected_at=None), "989120000001", "hi",
                                   _factory(calls), later)
    assert mid is None and calls["n"] == 0

    # 3) explicit, note-backed override → persisted + audit-logged → sender may now send.
    await se.enforce_for_assignment(db, "NEW", override=True,
                                    note="کمبود اکانت سالم؛ ریسک پذیرفته شد", now=later)
    cfgs = [x for x in db.added if isinstance(x, WarmupSenderConfig)]
    logs = [x for x in db.added if isinstance(x, WarmupHelperLog)]
    assert cfgs and cfgs[0].eligibility_overridden_at == later
    assert logs and logs[0].event_type == "eligibility_override"
    allowed2, reason2 = await se.sender_send_allowed(db, "NEW", later)
    assert allowed2 is True and reason2 == "overridden"
    calls2 = {"n": 0}
    mid2 = await he._send_as_sender(db, _acc("NEW", connected_at=None), "989120000001", "hi",
                                    _factory(calls2), later)
    assert mid2 == "MID" and calls2["n"] == 1


@pytest.mark.asyncio
async def test_grandfathered_account_unaffected_everywhere():
    """GUARDRAIL 3: a pre-existing account (NULL connect anchor) is never blocked by the cooldown."""
    old = _acc("OLD", connected_at=None)
    assert can_send_now(old, live_state="authorized", now=NOW) == (True, "ok")
    assert send_gate.connect_cooldown_active(old, NOW) is False


# ── wiring assertions ────────────────────────────────────────────────────────
def test_all_send_paths_consult_shared_gate():
    from app.services import campaign_runner, warmup_engine, warmup_helper_engine
    assert "gate_check(account)" in inspect.getsource(campaign_runner._deliver_message)
    assert "gate_check(sender" in inspect.getsource(warmup_engine.execute_action)
    assert "gate_check(sender)" in inspect.getsource(warmup_helper_engine._send_from_main)


def test_tc_sender_sites_route_through_eligibility_guard():
    from app.services import warmup_team_schedule, warmup_thankyou, warmup_cold_reply
    assert inspect.getsource(he).count("_send_as_sender(") >= 3        # ask/reminder + thank-you + def
    assert "_send_as_sender(db, sender" in inspect.getsource(warmup_team_schedule)
    assert "_send_as_sender(db, sender" in inspect.getsource(warmup_thankyou)
    # cold-reply (a young cold account answering) is intentionally NOT eligibility-gated.
    assert "_send_as_sender" not in inspect.getsource(warmup_cold_reply)


def test_single_source_of_truth_for_connect_cooldown():
    """warmup_reconnect_rest delegates to send_gate (no divergent second implementation)."""
    from app.services import warmup_reconnect_rest as wrr
    src = inspect.getsource(wrr)
    assert "send_gate.connect_cooldown_active" in src
    assert wrr.reconnect_rest_active(_acc("X", connected_at=NOW), NOW) is True
    assert wrr.reconnect_rest_active(_acc("Y", connected_at=None), NOW) is False
