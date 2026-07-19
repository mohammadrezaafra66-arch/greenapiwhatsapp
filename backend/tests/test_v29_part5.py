"""V29 PART 5 «همکاری تیمی» — automatic contextual reply FROM the cold account.

Proves:
  • a completed step schedules exactly one cold reply, timed with a NATURAL delay (never instant);
  • the reply is gated on the COLD account: within its 24h post-auth cooldown OR unhealthy → the
    reply is DEFERRED (not sent) until eligible;
  • an eligible cold account sends exactly one reply, re-arms the shared pacer, advances the
    thread, and clears the pending flag;
  • the reply text never leaks an identifier.
"""
import uuid
import random
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.services import warmup_cold_reply as ccr
from app.services import warmup_helper_thread as wt
from app.services import peer_pacer, send_gate
from app.models.warmup_helpers import WarmupHelper, WarmupHelperThread
from app.models.warmup_mesh import WarmupEnrollment
from app.models.account import AccountStatus

NOW = datetime(2026, 5, 4, 11, 0)


@pytest.fixture(autouse=True)
def _reset():
    peer_pacer.reset(); send_gate.clear_live_cache()
    yield
    peer_pacer.reset(); send_gate.clear_live_cache()


def _cold(iid="C1", cooldown_until=None):
    return SimpleNamespace(instance_id=iid, api_token="t", phone="989048249532", name=iid,
                           is_warm_peer=False, status=AccountStatus.active,
                           cooldown_until=cooldown_until, throttle_until=None, throttle_factor=1.0)


class _Res:
    def __init__(self, scalars=None):
        self._s = scalars or []
    def scalars(self):
        outer = self
        class _S:
            def all(s): return list(outer._s)
        return _S()
    def scalar_one_or_none(self): return self._s[0] if self._s else None


class _DB:
    def __init__(self, threads, cold, helper, enrollment):
        self.threads = threads; self.cold = cold; self.helper = helper; self.enr = enrollment
        self.commits = 0
    async def execute(self, q):
        sql = str(q).lower()
        if "warmup_helper_thread" in sql:
            return _Res(scalars=list(self.threads))
        if "warmup_enrollment" in sql:
            return _Res(scalars=[self.enr] if self.enr else [])
        if "accounts" in sql:
            return _Res(scalars=[self.cold] if self.cold else [])
        return _Res()
    def add(self, o): pass
    async def flush(self): pass
    async def commit(self): self.commits += 1
    async def get(self, model, pk): return self.helper


def _factory(store):
    def factory(iid, tok):
        c = MagicMock(); c.send_typing_ms = AsyncMock(return_value=True)
        async def _s(p, t): store["phone"] = p; store["text"] = t; return "MID"
        c.send_message = AsyncMock(side_effect=_s); return c
    return factory


# ── delay is natural (never instant) ─────────────────────────────────────────
def test_cold_reply_due_at_is_never_instant():
    due = ccr.cold_reply_due_at(NOW, random.Random(1))
    gap = (due - NOW).total_seconds()
    assert ccr.COLD_REPLY_MIN_DELAY_SECONDS <= gap <= ccr.COLD_REPLY_MAX_DELAY_SECONDS
    assert gap > 0


# ── 24h post-auth cooldown gate ──────────────────────────────────────────────
def test_post_auth_cooldown_gate():
    fresh = WarmupEnrollment(instance_id="C1", authorized_at=NOW - timedelta(hours=2))
    assert ccr.post_auth_cooldown_elapsed(fresh, NOW) is False        # only 2h → still cooling
    old = WarmupEnrollment(instance_id="C1", authorized_at=NOW - timedelta(hours=30))
    assert ccr.post_auth_cooldown_elapsed(old, NOW) is True
    assert ccr.post_auth_cooldown_elapsed(None, NOW) is False         # unknown → conservative


def test_cold_account_ready_combines_gates():
    old = WarmupEnrollment(instance_id="C1", authorized_at=NOW - timedelta(hours=30))
    ready, reason = ccr.cold_account_ready(_cold(), old, NOW)
    assert ready is True and reason == "ok"
    # health cooldown_until in the future → not ready even after 24h post-auth
    carded = _cold(cooldown_until=NOW + timedelta(days=1))
    ready2, reason2 = ccr.cold_account_ready(carded, old, NOW)
    assert ready2 is False and reason2 == "cooldown"


# ── generation never leaks identifiers ───────────────────────────────────────
@pytest.mark.asyncio
async def test_generate_cold_reply_rejects_leaky_ai():
    async def ai(*, topic, contact_name):
        return "شماره ۹۸۹۰۴۸۲۴۹۵۳۲ رو بگیر"      # long digit run → unsafe
    text, source = await ccr.generate_cold_reply(topic="پیگیری سفارش", contact_name="رضا",
                                                 ai_fn=ai, forbidden=("989048249532",),
                                                 rng=random.Random(1))
    assert source == "fallback"
    import re
    assert not re.search(r"\d{7,}", text)


# ── tick: cold account in cooldown DEFERS ────────────────────────────────────
@pytest.mark.asyncio
async def test_tick_defers_when_cold_in_cooldown(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    helper = WarmupHelper(name="رضا محمدی", phone="989111111111", sender_instance_id="P1")
    helper.id = uuid.uuid4()
    thread = WarmupHelperThread(helper_id=helper.id, cold_instance_id="C1", step_count=1,
                                status=wt.STATUS_ACTIVE, awaiting_reply=True,
                                topic_summary="پیگیری سفارش تلویزیون")
    thread.id = uuid.uuid4(); thread.pending_reply_at = NOW - timedelta(minutes=1)
    enr = WarmupEnrollment(instance_id="C1", authorized_at=NOW - timedelta(hours=2))  # cooling
    cold = _cold()
    store = {}
    res = await ccr.run_cold_reply_tick(_DB([thread], cold, helper, enr), now=NOW,
                                        client_factory=_factory(store), rng=random.Random(1))
    assert res["acted"] == 0 and res.get("deferred") is True
    assert thread.awaiting_reply is True          # still pending, not sent
    assert "phone" not in store


# ── tick: eligible cold account sends exactly one reply ──────────────────────
@pytest.mark.asyncio
async def test_tick_sends_when_eligible(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    helper = WarmupHelper(name="مریم کریمی", phone="989111111111", sender_instance_id="P1")
    helper.id = uuid.uuid4()
    thread = WarmupHelperThread(helper_id=helper.id, cold_instance_id="C1", step_count=1,
                                status=wt.STATUS_ACTIVE, awaiting_reply=True,
                                topic_summary="پیگیری سفارش تلویزیون")
    thread.id = uuid.uuid4(); thread.pending_reply_at = NOW - timedelta(minutes=1)
    enr = WarmupEnrollment(instance_id="C1", authorized_at=NOW - timedelta(hours=30))  # cleared
    cold = _cold()
    store = {}
    async def ai(*, topic, contact_name):
        return f"سلام {contact_name}، آره فرستادم، ممنون از پیگیریت"
    res = await ccr.run_cold_reply_tick(_DB([thread], cold, helper, enr), now=NOW,
                                        client_factory=_factory(store), ai_fn=ai, rng=random.Random(2))
    assert res["acted"] == 1 and res["sent"] is True
    assert store["phone"] == "989111111111"        # reply went to the contact
    assert thread.awaiting_reply is False and thread.pending_reply_at is None
    assert thread.step_count == 2                   # thread advanced
    # pacer re-armed for the cold instance
    assert peer_pacer.peer_ready("C1", ccr._to_utc_naive(NOW)) is False


# ── tick: nothing due ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_tick_nothing_due():
    res = await ccr.run_cold_reply_tick(_DB([], None, None, None), now=NOW)
    assert res["acted"] == 0 and res["due"] == 0
