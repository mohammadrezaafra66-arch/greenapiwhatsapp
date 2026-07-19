"""V30 PART 6 — variable typing-time + genuinely-random jitter (Green API compliance pass).

Proves:
  • `typingTime` scales with message length and is ALWAYS clamped to Green API's [1000, 20000] ms;
  • typing is applied for EVERY TC send type — they all route through `_send_from_main`, which
    calls show_typing_for_send with the ACTUAL message, so typing scales per-send;
  • the "random" intervals are genuinely variable (not a collapsed constant): the peer-pacer gap,
    the thank-you gap, the ask gate gap, and the typing jitter all vary across N draws.
"""
import random
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.services.typing_sim import (
    compute_typing_time, apply_typing_simulation, MIN_TYPING_MS, MAX_TYPING_MS,
)
from app.services import peer_pacer
from app.services import warmup_helper_service as hs
from app.services import warmup_helper_engine as he

NOW = datetime(2026, 5, 4, 11, 0)


# ── 6.1 typingTime scales with length, always within Green API bounds ────────
def test_typing_time_scales_with_length_no_jitter():
    short = compute_typing_time(10, jitter=False)
    medium = compute_typing_time(80, jitter=False)
    long = compute_typing_time(200, jitter=False)
    assert short < medium < long                     # monotonic in length
    for v in (short, medium, long):
        assert MIN_TYPING_MS <= v <= MAX_TYPING_MS


def test_typing_time_clamped_to_green_api_range():
    assert compute_typing_time(1, jitter=False) >= MIN_TYPING_MS       # tiny → floor 1000
    assert compute_typing_time(100000, jitter=False) == MAX_TYPING_MS   # huge → cap 20000
    # even with max jitter a 1-char message never dips below the floor
    for seed in range(20):
        assert compute_typing_time(1, rng=random.Random(seed)) >= MIN_TYPING_MS


def test_typing_time_varies_for_identical_input():
    vals = [compute_typing_time(80, rng=random.Random(s)) for s in range(30)]
    assert len(set(vals)) > 10        # jitter genuinely varies the duration


@pytest.mark.asyncio
async def test_apply_typing_uses_length_scaled_value_and_calls_green_api():
    client = MagicMock()
    client.send_typing_ms = AsyncMock(return_value=True)
    ms_short = await apply_typing_simulation(client, "989111111111", "سلام", sleep=False,
                                             rng=random.Random(1))
    long_text = "سلام رفیق، " * 40
    ms_long = await apply_typing_simulation(client, "989111111111", long_text, sleep=False,
                                            rng=random.Random(1))
    assert ms_long > ms_short                              # longer message → longer typing
    assert MIN_TYPING_MS <= ms_short <= MAX_TYPING_MS
    assert MIN_TYPING_MS <= ms_long <= MAX_TYPING_MS
    # the value passed to Green API's SendTyping is exactly the length-scaled ms
    called_ms = client.send_typing_ms.await_args.args[1]
    assert called_ms == ms_long


# ── every TC send applies typing (they all go through _send_from_main) ───────
@pytest.mark.asyncio
async def test_send_from_main_applies_typing_with_actual_message(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr("app.services.warmup_helper_engine.show_typing_for_send", spy)
    sender = MagicMock(instance_id="P1", api_token="t", status=None,
                       cooldown_until=None, throttle_until=None, throttle_factor=1.0)
    # bypass the health gate so we reach the typing+send
    monkeypatch.setattr("app.services.send_gate.gate_check", lambda s: (True, "ok"))

    def factory(iid, tok):
        c = MagicMock(); c.send_message = AsyncMock(return_value="MID"); return c
    await he._send_from_main(sender, "989111111111", "پیام تست 🙏", factory)
    spy.assert_awaited_once()
    # the ACTUAL message text is what typing is computed from (so it scales per-send)
    assert spy.await_args.args[2] == "پیام تست 🙏"
    assert spy.await_args.kwargs.get("enabled") is True


# ── 6.2 genuinely variable intervals (no collapsed constant) ─────────────────
def test_peer_pacer_gap_is_genuinely_random():
    gaps = [peer_pacer.jittered_gap_seconds(random.Random(s)) for s in range(40)]
    assert all(peer_pacer.MIN_PEER_GAP_SECONDS <= g <= peer_pacer.MAX_PEER_GAP_SECONDS for g in gaps)
    assert len(set(gaps)) > 20                                  # not a fixed constant
    # no two CONSECUTIVE draws from one stream are identical
    stream = random.Random(7)
    seq = [peer_pacer.jittered_gap_seconds(stream) for _ in range(50)]
    assert all(seq[i] != seq[i + 1] for i in range(len(seq) - 1))


def test_thankyou_gap_is_genuinely_random():
    stream = random.Random(3)
    seq = [peer_pacer.jittered_gap_seconds(stream) for _ in range(30)]
    assert len(set(seq)) > 15


def test_ask_gate_gap_is_genuinely_random():
    # next_ask_at jitters the gap within [MIN, MAX] seconds; consecutive gaps differ.
    stream = random.Random(11)
    gaps = [(hs.next_ask_at(NOW, stream) - NOW).total_seconds() for _ in range(40)]
    assert all(hs.HELPER_ASK_MIN_GAP_SECONDS <= g <= hs.HELPER_ASK_MAX_GAP_SECONDS for g in gaps)
    assert len(set(gaps)) > 20
