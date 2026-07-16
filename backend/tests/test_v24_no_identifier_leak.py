"""V24 — warm-up messages must NEVER contain an internal account identifier or label.

Regression against the ban-risk bug where the account's internal label (e.g.
"9048249533 گوشی زینب شخصی") was passed as the recipient's name and the AI echoed it
into the body ("برای 9048249532 جان بگم که..."). These tests prove:

  * the hard `message_is_safe` filter rejects phone/instance-id digit runs and label chunks
  * `name_for_instance` never derives a name from the account label/number
  * `generate_mesh_message` rejects AI output that leaks an identifier and falls back
  * the fallback pool is identifier-free by construction
  * identifier-tainted history lines are not fed back into the prompt
"""
import random
import pytest

from app.services import warmup_content as content
from app.services.warmup_content import (
    message_is_safe, looks_like_identifier, generate_mesh_message,
    assemble_fallback_message, HUMAN_NAMES,
)
from app.services.warmup_ai import name_for_instance, build_warmup_ai_fn


def test_long_digit_runs_are_identifiers():
    assert looks_like_identifier("سلام 9048249532 جان")
    assert looks_like_identifier("۹۰۴۸۲۴۹۵۳۳ گوشی")          # Persian digits too
    assert looks_like_identifier("770022682898")
    # Legit product numbers are NOT identifiers.
    assert not looks_like_identifier("کولر گازی ۱۸۰۰۰ موجوده؟")
    assert not looks_like_identifier("تلویزیون ۵۵ اینچ")
    assert not looks_like_identifier("سلام، خوب هستی؟")


def test_message_is_safe_rejects_the_reported_leaks():
    # The exact shapes reported in the bug.
    assert not message_is_safe("برای 9048249532 جان بگم که موجوده")
    assert not message_is_safe("سلام 9048249533 گوشی زینب شخصی، قیمت...")
    # And rejects label chunks even without digits, when the label is known forbidden.
    forbidden = ("9048249533 گوشی زینب شخصی",)
    assert not message_is_safe("سلام گوشی جان خوبی؟", forbidden)
    assert not message_is_safe("شخصی عزیز بار رسید", forbidden)
    # Clean human chat passes.
    assert message_is_safe("سلام، خوب هستی؟", forbidden)
    assert message_is_safe("قیمت یخچال ساید امروز چنده؟", forbidden)
    assert message_is_safe("رضا جان صبح بخیر 🌹", forbidden)


def test_name_for_instance_never_uses_the_label():
    # Only ever a curated human first name or None — never the instance id / a number.
    for iid in ("9048249532", "770022682898", "7105325764", "9048249533"):
        n = name_for_instance(iid)
        assert n is None or n in HUMAN_NAMES
        assert n != iid
    # Stable per instance.
    assert name_for_instance("770022682898") == name_for_instance("770022682898")


@pytest.mark.asyncio
async def test_ai_leak_is_rejected_and_falls_back():
    """If the AI ever emits an identifier, it must be rejected and we fall back clean."""
    async def leaky_chat(system, user, max_tokens, temperature):
        return "سلام 9048249533 گوشی زینب شخصی، قیمت یخچال؟"

    ai_fn = build_warmup_ai_fn(chat_fn=leaky_chat)
    forbidden = ("9048249533 گوشی زینب شخصی", "9048249533")
    text, source = await generate_mesh_message(
        ai_fn=ai_fn, forbidden=forbidden, rng=random.Random(1))
    assert source == "fallback"                       # leak rejected → fallback
    assert message_is_safe(text, forbidden)
    assert not looks_like_identifier(text)


@pytest.mark.asyncio
async def test_label_name_argument_is_dropped_not_echoed():
    """Even if a caller passes the raw label as `name`, it must not reach the message."""
    async def echo_name_chat(system, user, max_tokens, temperature):
        # A naive model would echo whatever "name" it was given; prove it isn't in the prompt.
        assert "گوشی زینب شخصی" not in user
        assert "9048249533" not in user
        return "سلام، امروز بازار چطوره؟"

    ai_fn = build_warmup_ai_fn(chat_fn=echo_name_chat)
    text, source = await generate_mesh_message(
        ai_fn=ai_fn, name="9048249533 گوشی زینب شخصی", rng=random.Random(2))
    assert source == "ai"
    assert message_is_safe(text)


def test_fallback_pool_is_identifier_free():
    r = random.Random(7)
    for _ in range(500):
        msg = assemble_fallback_message(name="9048249533 گوشی زینب شخصی",
                                        forbidden=("9048249533 گوشی زینب شخصی",), rng=r)
        assert message_is_safe(msg), msg
        assert not looks_like_identifier(msg), msg


@pytest.mark.asyncio
async def test_tainted_history_not_echoed_into_prompt():
    seen = {}

    async def capture(system, user, max_tokens, temperature):
        seen["user"] = user
        return "بله موجوده، فردا می‌فرستم 👍"

    ai_fn = build_warmup_ai_fn(chat_fn=capture)
    await generate_mesh_message(
        ai_fn=ai_fn,
        history=["سلام 9048249533 گوشی زینب شخصی", "قیمت یخچال ساید؟"],
        forbidden=("9048249533 گوشی زینب شخصی",),
        rng=random.Random(3))
    # The clean history line survives; the tainted one is filtered out of the prompt.
    assert "قیمت یخچال ساید؟" in seen["user"]
    assert "9048249533" not in seen["user"]
    assert "گوشی زینب شخصی" not in seen["user"]
