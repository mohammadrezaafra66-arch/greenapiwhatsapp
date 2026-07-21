"""V38 — the reminder-message generator must be reminder-TONED and leak-safe.

Locks in that a generated «همکاری تیمی» reminder, across a sample of generations and for BOTH the
AI path and the fallback path:
  • carries reminder-signaling language (so it reads like a reminder, not a fresh first ask),
  • carries at least one curated reminder/urgency emoji,
  • never leaks an identifier (phone / instance id / label) — the UNCHANGED V24 filter still holds,
  • is DISTINGUISHABLE in tone from what the ASK generator produces for the same contact.
"""
import random
import pytest

from app.services.warmup_reminder import (
    generate_reminder, has_reminder_signal, has_reminder_emoji, REMINDER_EMOJI,
    build_reminder_fallback,
)
from app.services.warmup_content import message_is_safe, looks_like_identifier
from app.services.outreach_message import generate_thread_ask_message


NAMES = ["مینا معزز", "پروین رضایی", "میترا افرا", "غزاله صالحی", "جبار افرا", "پورچیستا سادات"]

# Identifiers that must NEVER surface in a reminder body.
FORBIDDEN = ("770022683838", "7105325764", "989199609645", "گوشی زینب شخصی")


def _ai_reminder(text):
    """A fake reminder ai_fn (signature `(*, contact_name)`) that returns a fixed string."""
    async def _fn(*, contact_name):
        return text
    return _fn


def _ai_ask(text):
    """A fake ask ai_fn (thread signature) that returns a fixed string."""
    async def _fn(*, name, topic, step_count, brief, profile_line):
        return text
    return _fn


@pytest.mark.asyncio
async def test_ai_reminder_is_reminder_toned_emoji_and_leak_safe():
    # A realistic, reminder-toned AI output for every name → accepted as "ai", signal + emoji + safe.
    for i, name in enumerate(NAMES):
        r = random.Random(i)
        ai_text = f"سلام {name} جان، این پیام فقط جهت یادآوریه؛ هنوز منتظر همون پیامتم ⏰"
        text, source = await generate_reminder(
            contact_name=name, ai_fn=_ai_reminder(ai_text), forbidden=FORBIDDEN, rng=r)
        assert source == "ai"
        assert has_reminder_signal(text), f"no reminder signal: {text}"
        assert has_reminder_emoji(text), f"no reminder emoji: {text}"
        assert message_is_safe(text, FORBIDDEN)
        assert not looks_like_identifier(text)


@pytest.mark.asyncio
async def test_ai_output_without_reminder_signal_is_rejected_falls_back():
    # An AI line that reads like a fresh ask (no reminder signal) is rejected → safe fallback used,
    # and the fallback still carries a reminder signal + reminder emoji.
    r = random.Random(7)
    fresh_ask_like = "سلام مینا جان، یه لطف کوچیک ازت داشتم 🙏"  # no reminder-signal word
    text, source = await generate_reminder(
        contact_name="مینا معزز", ai_fn=_ai_reminder(fresh_ask_like), forbidden=FORBIDDEN, rng=r)
    assert source == "fallback"
    assert has_reminder_signal(text)
    assert has_reminder_emoji(text)


@pytest.mark.asyncio
async def test_ai_output_leaking_identifier_is_rejected():
    # An AI line containing a forbidden instance id is rejected by the UNCHANGED leak filter → fallback.
    r = random.Random(3)
    leaky = "سلام مینا، یادت نره؛ شماره ما 770022683838 هست ⏰"
    text, source = await generate_reminder(
        contact_name="مینا معزز", ai_fn=_ai_reminder(leaky), forbidden=FORBIDDEN, rng=r)
    assert source == "fallback"
    assert message_is_safe(text, FORBIDDEN)
    assert "770022683838" not in text


@pytest.mark.asyncio
async def test_fallback_sample_always_signal_emoji_and_safe():
    # Across many fallback generations for many names, EVERY one is reminder-toned + emoji + leak-safe.
    for seed in range(60):
        r = random.Random(seed)
        name = NAMES[seed % len(NAMES)]
        text, source = await generate_reminder(
            contact_name=name, ai_fn=None, forbidden=FORBIDDEN, rng=r)
        assert source == "fallback"
        assert has_reminder_signal(text), f"seed {seed}: {text}"
        assert has_reminder_emoji(text), f"seed {seed}: {text}"
        assert message_is_safe(text, FORBIDDEN), f"seed {seed}: {text}"


@pytest.mark.asyncio
async def test_reminder_is_distinguishable_in_tone_from_ask():
    # For the SAME contact, the ASK body carries NO reminder-signal, while the REMINDER body does —
    # so a recipient can tell a reminder from a fresh ask. Ask generator is exercised unchanged.
    name = "پروین رضایی"
    ask_text = "سلام پروین رضایی جان، درباره‌ی همکاری یه زحمت کوچیک برات داشتم 🙏"
    ask_msg, ask_src = await generate_thread_ask_message(
        brief=None, contact={"name": name}, topic="همکاری", step_count=0,
        cold_phone_digits=[], ai_fn=_ai_ask(ask_text), forbidden=FORBIDDEN, rng=random.Random(1))
    ask_body = ask_msg.split("\n", 1)[0]
    assert ask_src == "ai"
    assert not has_reminder_signal(ask_body), f"ask should not read as a reminder: {ask_body}"

    rem_text = "سلام پروین جان، فقط جهت یادآوری؛ هنوز منتظر جوابتم ⏳"
    rem_body, rem_src = await generate_reminder(
        contact_name=name, ai_fn=_ai_reminder(rem_text), forbidden=FORBIDDEN, rng=random.Random(1))
    assert rem_src == "ai"
    assert has_reminder_signal(rem_body)
    assert has_reminder_emoji(rem_body)


@pytest.mark.asyncio
async def test_emoji_backstop_appends_reminder_emoji_when_missing():
    # An accepted AI reminder that signals reminder tone but has only a generic/no emoji still gets a
    # curated reminder emoji appended (never rejected for that alone).
    r = random.Random(0)
    no_emoji = "سلام مینا جان، فقط جهت یادآوری؛ هنوز منتظر همون پیامتم"
    text, source = await generate_reminder(
        contact_name="مینا معزز", ai_fn=_ai_reminder(no_emoji), forbidden=FORBIDDEN, rng=r)
    assert source == "ai"
    assert has_reminder_emoji(text)
    assert any(text.endswith(e) for e in REMINDER_EMOJI)
