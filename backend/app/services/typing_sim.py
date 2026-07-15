"""V17 PART 1 — human-like typing simulation for the send path.

Green API recommends showing the "typing…" (or voice "recording…") indicator before
a send so messages look human. Two mechanisms exist:

  1. Per-message `typingTime` on SendMessage (1000–20000 ms) — OVERRIDES the instance
     `autoTyping` setting for that send.
  2. A standalone `SendTyping` call (chatId, typingTime 1000–20000, optional
     typingType="recording") BEFORE the send.

We use mechanism 2 (SendTyping first, then send) so the message payload itself is
untouched. The duration is derived from message length and ALWAYS randomized, so it is
never a constant fingerprint.

Everything here is pure/​injectable so it unit-tests without a live Green API or DB.
"""
import asyncio
import logging
import random

logger = logging.getLogger("afrakala.typing")

# Green API hard limits for the typingTime field (milliseconds).
MIN_TYPING_MS = 1000
MAX_TYPING_MS = 20000

# autoTyping:2 == "10 chars/sec" in Green API terms → chars/sec = autoTyping * 5.
DEFAULT_AUTO_TYPING = 2

# The voice-recording indicator, used occasionally to diversify the fingerprint.
TYPING_TYPE_RECORDING = "recording"


def compute_typing_time(text_length: int, auto_typing: int = DEFAULT_AUTO_TYPING,
                        jitter: bool = True, rng: random.Random | None = None) -> int:
    """Human-like typing duration in ms for a message of `text_length` chars.

    Base follows Green API's formula `(len / (autoTyping*5)) * 1000`. A random 0.7–1.4×
    multiplier is applied (unless jitter=False) so the value VARIES for identical input —
    a constant typingTime is itself a bot fingerprint. The result is always clamped to
    the valid [1000, 20000] ms range.
    """
    chars_per_sec = max(1, int(auto_typing) * 5)
    base_ms = (max(1, int(text_length)) / chars_per_sec) * 1000.0
    if jitter:
        r = rng or random
        base_ms *= r.uniform(0.7, 1.4)
    return int(max(MIN_TYPING_MS, min(MAX_TYPING_MS, base_ms)))


def pick_typing_type(recording_prob: float = 0.08,
                     rng: random.Random | None = None) -> str | None:
    """Occasionally return "recording" (voice indicator); otherwise None (plain typing).
    Low probability by default so most turns are text typing."""
    r = rng or random
    return TYPING_TYPE_RECORDING if r.random() < max(0.0, recording_prob) else None


async def apply_typing_simulation(client, phone: str, message: str,
                                  auto_typing: int = DEFAULT_AUTO_TYPING,
                                  recording_prob: float = 0.08,
                                  sleep: bool = True,
                                  rng: random.Random | None = None) -> int:
    """Show the typing/recording indicator for a length-scaled, jittered duration, then
    (optionally) wait that long so the indicator is actually visible before the caller
    sends. Non-fatal: any Green API error is swallowed so it never blocks a send.
    Returns the typingTime (ms) used — handy for tests/telemetry."""
    typing_ms = compute_typing_time(len(message or ""), auto_typing=auto_typing, rng=rng)
    typing_type = pick_typing_type(recording_prob, rng=rng)
    try:
        await client.send_typing_ms(phone, typing_ms, typing_type=typing_type)
        if sleep:
            await asyncio.sleep(typing_ms / 1000.0)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("typing simulation failed (non-fatal): %s", e)
    return typing_ms


async def _legacy_typing(client, phone: str) -> None:
    """V16 behavior, preserved EXACTLY for the typing-simulation-OFF path: show typing
    for a random 2–4s using the old SendTyping shape, then wait. Byte-identical to V16."""
    try:
        typing_secs = random.randint(2, 4)
        await client.send_typing(phone, typing_secs)
        await asyncio.sleep(typing_secs)
    except Exception:
        pass  # Non-fatal — never block sending


async def show_typing_for_send(client, phone: str, message: str, enabled: bool) -> None:
    """Single entry point used by the campaign send path.

    enabled=False → the untouched V16 typing (guardrail: byte-identical behavior).
    enabled=True  → the new length-scaled, jittered, occasionally-"recording" simulation.
    """
    if enabled:
        await apply_typing_simulation(client, phone, message)
    else:
        await _legacy_typing(client, phone)
