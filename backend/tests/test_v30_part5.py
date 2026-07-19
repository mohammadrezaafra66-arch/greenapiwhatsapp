"""V30 PART 5 — varied AI content (emoji, tone) + staggered thank-yous.

Proves:
  • ask-messages always carry emoji (AI-prompted; emoji backstop) and are anti-repeat vs `recent`;
  • thank-you messages are AI-generated, varied, warm, emoji-bearing, leak-safe (V24), anti-repeat;
  • a burst of completions for one contact does NOT fire simultaneous thank-yous: the first is
    inline, the overflow is SCHEDULED (awaiting_thankyou) and the tick sends them one-per-tick,
    staggered by the thank-you pacer floor.
"""
import uuid
import random
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest

from app.services import warmup_thankyou as ty
from app.services import outreach_message as om
from app.services import peer_pacer
from app.services.warmup_content import has_emoji, message_is_safe

NOW = datetime(2026, 5, 4, 11, 0)


# ── emoji helper ──────────────────────────────────────────────────────────────
def test_has_emoji():
    assert has_emoji("سلام 🙏") is True
    assert has_emoji("ممنون 🌹") is True
    assert has_emoji("سلام دوست من") is False
    assert has_emoji("") is False


# ── ask-messages: emoji guaranteed + anti-repeat ─────────────────────────────
@pytest.mark.asyncio
async def test_ask_message_always_has_emoji_even_without_ai():
    # No ai_fn → templated fallback path; every fallback carries an emoji.
    for seed in range(6):
        msg, source = await om.generate_thread_ask_message(
            brief="سلام بده", contact={"name": "رضا محمدی"}, topic="پیگیری سفارش",
            step_count=0, cold_phone_digits=["989048249532"], ai_fn=None,
            rng=random.Random(seed))
        assert has_emoji(msg)
        assert source == "fallback"


@pytest.mark.asyncio
async def test_ask_message_emoji_backstop_for_emojiless_ai():
    async def ai_no_emoji(*, name, topic, step_count, brief, profile_line):
        return f"سلام {name}، درباره‌ی {topic} یه لطف کوچیک داشتم"   # deliberately no emoji
    msg, source = await om.generate_thread_ask_message(
        brief=None, contact={"name": "رضا محمدی"}, topic="پیگیری سفارش", step_count=1,
        cold_phone_digits=["989048249532"], ai_fn=ai_no_emoji, rng=random.Random(1))
    assert source == "ai"
    assert has_emoji(msg)               # backstop appended a natural emoji


@pytest.mark.asyncio
async def test_ask_message_anti_repeat_vs_recent():
    async def ai_same(*, name, topic, step_count, brief, profile_line):
        return f"سلام {name}، درباره‌ی {topic} یه لطف کوچیک 🙏"
    recent = ["سلام رضا محمدی، درباره‌ی پیگیری سفارش یه لطف کوچیک 🙏"]
    msg, source = await om.generate_thread_ask_message(
        brief=None, contact={"name": "رضا محمدی"}, topic="پیگیری سفارش", step_count=1,
        cold_phone_digits=["989048249532"], ai_fn=ai_same, recent=recent, rng=random.Random(2))
    # AI candidate is a near-duplicate of `recent` → rejected → safe fallback used instead.
    assert source == "fallback"
    assert has_emoji(msg)


# ── thank-you generation: AI, varied, emoji, leak-safe, anti-repeat ──────────
@pytest.mark.asyncio
async def test_thankyou_ai_used_when_valid():
    async def ai(*, contact_name):
        return f"خیلی ممنونم {contact_name} جان، لطف کردی 🌹"
    text, source = await ty.generate_thank_you(contact_name="رضا", ai_fn=ai, rng=random.Random(1))
    assert source == "ai" and has_emoji(text) and "رضا" in text


@pytest.mark.asyncio
async def test_thankyou_rejects_emojiless_and_leaky_ai_then_falls_back():
    async def ai_bad(*, contact_name):
        return "ممنون از شما 770022683809"     # leaks an instance id (V24) → rejected
    text, source = await ty.generate_thank_you(
        contact_name="رضا", ai_fn=ai_bad, forbidden=("770022683809",), rng=random.Random(3))
    assert source == "fallback"
    assert has_emoji(text) and message_is_safe(text, ("770022683809",))


def test_thankyou_fallbacks_are_varied_and_all_emoji_and_thanks():
    seen = set()
    for seed in range(20):
        t = ty.build_thankyou_fallback("رضا", random.Random(seed))
        assert has_emoji(t) and "ممنون" in t
        seen.add(t)
    assert len(seen) >= 3          # genuinely varied


# ── staggering ────────────────────────────────────────────────────────────────
def test_thankyou_due_at_staggers_by_floor():
    d0 = ty.thankyou_due_at(NOW, ahead_count=0, rng=random.Random(1))
    d1 = ty.thankyou_due_at(NOW, ahead_count=1, rng=random.Random(1))
    d2 = ty.thankyou_due_at(NOW, ahead_count=2, rng=random.Random(1))
    # each additional queued thank-you pushes the due time out by >= the anti-ban floor
    assert (d1 - d0).total_seconds() >= peer_pacer.MIN_PEER_GAP_SECONDS
    assert (d2 - d1).total_seconds() >= peer_pacer.MIN_PEER_GAP_SECONDS


def test_thankyou_pacer_defers_second_thankyou():
    peer_pacer.reset()
    assert peer_pacer.thankyou_ready("P1", NOW) is True
    peer_pacer.record_thankyou("P1", NOW, random.Random(1))
    # a second thank-you moments later is NOT ready (staggered)
    assert peer_pacer.thankyou_ready("P1", NOW + timedelta(seconds=3)) is False
    # but a DIFFERENT sender is unaffected
    assert peer_pacer.thankyou_ready("P2", NOW) is True
    # and after the floor elapses it's ready again
    assert peer_pacer.thankyou_ready("P1", NOW + timedelta(seconds=30)) is True


@pytest.mark.asyncio
async def test_thankyou_tick_sends_one_and_defers_rest(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    peer_pacer.reset()
    # Two threads for the SAME sender are due for a thank-you at the same instant.
    helper = SimpleNamespace(id=uuid.uuid4(), name="رضا محمدی", phone="989111111111",
                             sender_instance_id="P1")
    th1 = SimpleNamespace(id=uuid.uuid4(), helper_id=helper.id, cold_instance_id="C1",
                          awaiting_thankyou=True, pending_thankyou_at=NOW - timedelta(seconds=1))
    th2 = SimpleNamespace(id=uuid.uuid4(), helper_id=helper.id, cold_instance_id="C2",
                          awaiting_thankyou=True, pending_thankyou_at=NOW - timedelta(seconds=1))
    sender = SimpleNamespace(instance_id="P1", api_token="t", phone="989000", name="P1",
                             is_warm_peer=True, status=__import__("app.models.account", fromlist=["AccountStatus"]).AccountStatus.active,
                             cooldown_until=None, throttle_until=None, throttle_factor=1.0)

    class _Res:
        def __init__(self, scalars): self._s = scalars
        def scalars(self):
            s = self._s
            class _S:
                def all(self_): return list(s)
            return _S()

    class _DB:
        def __init__(self): self.added = []; self.commits = 0
        def _sql(self, q):
            try: return str(q.compile(compile_kwargs={"literal_binds": True})).lower()
            except Exception: return str(q).lower()
        async def execute(self, q):
            sql = self._sql(q)
            if "warmup_helper_thread" in sql:
                return _Res([th1, th2])
            if "accounts" in sql:
                return _Res([sender])
            return _Res([])
        def add(self, o): self.added.append(o)
        async def commit(self): self.commits += 1
        async def get(self, model, pk):
            return helper if pk == helper.id else None

    store = {}
    def factory(iid, tok):
        c = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
        c.send_typing_ms = AsyncMock(return_value=True)
        async def _s(p, t): store.setdefault("sends", []).append((p, t)); return "MID"
        c.send_message = AsyncMock(side_effect=_s); return c

    async def ai(*, contact_name): return f"ممنون {contact_name} جان 🙏"

    # First tick: sends exactly ONE thank-you, records the thank-you pacer.
    r1 = await ty.run_thankyou_tick(_DB(), now=NOW, client_factory=factory, ai_fn=ai,
                                    rng=random.Random(1))
    assert r1["acted"] == 1 and len(store.get("sends", [])) == 1
    # Second tick at the SAME instant: sender's thank-you pacer NOT ready → nothing sent (deferred).
    r2 = await ty.run_thankyou_tick(_DB(), now=NOW, client_factory=factory, ai_fn=ai,
                                    rng=random.Random(2))
    assert r2["acted"] == 0
    assert len(store.get("sends", [])) == 1     # still only one thank-you — no burst
