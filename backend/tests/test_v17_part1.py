"""V17 PART 1 — typing simulation on the send path.

Covers: randomized typingTime (always 1000–20000, varies, scales with length),
occasional "recording" type, the SendTyping-when-enabled / legacy-when-disabled gate,
and the byte-identical guardrail (message text never depends on typing simulation).
"""
import asyncio
import random
import pytest
from types import SimpleNamespace

from app.services import typing_sim
from app.services.typing_sim import (
    compute_typing_time, pick_typing_type, apply_typing_simulation,
    show_typing_for_send, MIN_TYPING_MS, MAX_TYPING_MS, TYPING_TYPE_RECORDING,
)


# ── compute_typing_time: bounds, variance, length scaling ───────────────────
def test_typing_time_always_within_bounds():
    rng = random.Random(1234)
    for length in (0, 1, 5, 50, 200, 1000, 100000):
        for _ in range(50):
            tt = compute_typing_time(length, rng=rng)
            assert MIN_TYPING_MS <= tt <= MAX_TYPING_MS


def test_typing_time_varies_for_same_length():
    """A constant typingTime is itself a bot fingerprint — jitter must make it vary."""
    rng = random.Random(42)
    vals = {compute_typing_time(120, rng=rng) for _ in range(30)}
    assert len(vals) > 1  # not a constant


def test_typing_time_scales_with_length():
    """With jitter off, a longer message yields a longer (or equal, once clamped) time."""
    short = compute_typing_time(20, jitter=False)
    mid = compute_typing_time(120, jitter=False)
    long = compute_typing_time(600, jitter=False)
    assert short <= mid <= long
    assert mid > short  # genuinely scales in the unclamped middle range


def test_typing_time_clamps_tiny_and_huge():
    assert compute_typing_time(1, jitter=False) == MIN_TYPING_MS      # tiny → floor
    assert compute_typing_time(10_000, jitter=False) == MAX_TYPING_MS  # huge → cap


# ── pick_typing_type: occasional recording ──────────────────────────────────
def test_pick_typing_type_mostly_none_sometimes_recording():
    rng = random.Random(7)
    picks = [pick_typing_type(0.08, rng=rng) for _ in range(2000)]
    n_rec = sum(1 for p in picks if p == TYPING_TYPE_RECORDING)
    assert 0 < n_rec < len(picks)          # sometimes, but not always
    assert n_rec / len(picks) < 0.25        # stays low-frequency


def test_pick_typing_type_zero_prob_never_recording():
    rng = random.Random(7)
    assert all(pick_typing_type(0.0, rng=rng) is None for _ in range(100))


# ── the send-path gate: SendTyping when enabled, legacy when disabled ───────
class _FakeClient:
    def __init__(self):
        self.calls = []

    async def send_typing_ms(self, phone, typing_time_ms, typing_type=None):
        self.calls.append(("send_typing_ms", phone, typing_time_ms, typing_type))
        return True

    async def send_typing(self, phone, duration_seconds):
        self.calls.append(("send_typing", phone, duration_seconds))
        return True


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _fast(_):
        return None
    monkeypatch.setattr(typing_sim.asyncio, "sleep", _fast)


def test_apply_typing_simulation_calls_send_typing_ms():
    client = _FakeClient()
    used = asyncio.run(apply_typing_simulation(client, "989120000000", "سلام دوست من"))
    assert MIN_TYPING_MS <= used <= MAX_TYPING_MS
    assert client.calls and client.calls[0][0] == "send_typing_ms"
    assert client.calls[0][2] == used


def test_show_typing_enabled_uses_new_path_only():
    client = _FakeClient()
    asyncio.run(show_typing_for_send(client, "989120000000", "متن تست", enabled=True))
    methods = {c[0] for c in client.calls}
    assert "send_typing_ms" in methods
    assert "send_typing" not in methods  # never the legacy shape when ON


def test_show_typing_disabled_uses_legacy_path_only():
    """Guardrail: OFF path is byte-identical to V16 (legacy send_typing, no new call)."""
    client = _FakeClient()
    asyncio.run(show_typing_for_send(client, "989120000000", "متن تست", enabled=False))
    methods = {c[0] for c in client.calls}
    assert "send_typing" in methods
    assert "send_typing_ms" not in methods


def test_typing_never_raises_on_client_error():
    class _BadClient:
        async def send_typing_ms(self, *a, **k):
            raise RuntimeError("green api down")
    # Must not raise — typing is strictly non-fatal.
    used = asyncio.run(apply_typing_simulation(_BadClient(), "989120000000", "x"))
    assert MIN_TYPING_MS <= used <= MAX_TYPING_MS


# ── byte-identical guardrail: message text is independent of typing sim ─────
def test_message_text_independent_of_typing_flag():
    """build_message_text must produce identical output regardless of typing_simulation —
    typing simulation only affects the indicator, never the message bytes."""
    from app.services.campaign_runner import build_message_text

    def _campaign(typing):
        return SimpleNamespace(
            use_gpt=False, gpt_prompt=None, message_template="سلام {{first_name}} جان",
            opening_mode="none", opening_line=None, opening_variants=None,
            emoji_level="medium", show_product_prices=False, include_opt_out=False,
            opt_out_text=None, append_seller_name=False, seller_name=None,
            append_seller_phone=False, seller_phone=None, seller_phone2=None,
            append_date=False, use_rich_formatting=False, campaign_scope="pv",
            product_detail_level="medium", include_products=False,
            typing_simulation=typing,
        )
    contact = SimpleNamespace(first_name="علی", last_name="رضایی", city="", province="")
    off = asyncio.run(build_message_text(_campaign(False), contact, [], None, "سلام {{first_name}} جان", False))
    on = asyncio.run(build_message_text(_campaign(True), contact, [], None, "سلام {{first_name}} جان", False))
    assert off == on
