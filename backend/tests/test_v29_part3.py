"""V29 PART 3 «همکاری تیمی» — conversation threads + thread-aware personalized generation.

Proves:
  • derive_topic keeps an established topic on step 2+ and invents a product-relevant one on
    step 0;
  • advance_thread bumps step_count / stamps last_step_at / updates topic;
  • generated ask-messages include the real FULL name, reference job/benefit info when present,
    continue the topic on step 2+, never reference more than 2 cold accounts, never leak an
    identifier, carry correct wa.me links, and use the fallback safely when AI is unavailable.
"""
import re
import uuid
import random
from datetime import datetime
import pytest

from app.services import warmup_helper_thread as wt
from app.services import outreach_message as om
from app.models.warmup_helpers import WarmupHelperThread


# ── pure: derive_topic ────────────────────────────────────────────────────────
def test_derive_topic_keeps_established_topic():
    assert wt.derive_topic(brief="سلام بده", product="یخچال",
                           existing_topic="پیگیری سفارش تلویزیون", step_count=3) \
        == "پیگیری سفارش تلویزیون"


def test_derive_topic_step0_uses_product():
    t = wt.derive_topic(brief="سلام بده", product="تلویزیون ۵۵ اینچ",
                        existing_topic=None, step_count=0)
    assert "تلویزیون ۵۵ اینچ" in t and t.startswith("پیگیری سفارش")


def test_derive_topic_step0_falls_back_to_brief_then_generic():
    assert wt.derive_topic(brief="یه لطف بخواه", product=None, existing_topic=None,
                           step_count=0) == "یه لطف بخواه"
    assert wt.derive_topic(brief=None, product=None, existing_topic=None, step_count=0) \
        == "احوال‌پرسی و یک درخواست کوچک"


# ── advance_thread ────────────────────────────────────────────────────────────
def test_advance_thread_bumps_and_stamps():
    th = WarmupHelperThread(helper_id=uuid.uuid4(), cold_instance_id="C1", step_count=0)
    now = datetime(2026, 5, 4, 11, 0)
    wt.advance_thread(th, "پیگیری سفارش یخچال", now)
    assert th.step_count == 1 and th.topic_summary == "پیگیری سفارش یخچال"
    assert th.last_step_at == now
    wt.advance_thread(th, "پیگیری سفارش یخچال", now)
    assert th.step_count == 2


# ── generation: real full name always present ────────────────────────────────
CONTACT = {"name": "رضا محمدی", "job_title": "کارشناس فروش", "years_experience": 6,
           "personal_benefit_note": "تخفیف پرسنلی روی محصولات"}


@pytest.mark.asyncio
async def test_generated_message_includes_full_name_fallback():
    # No AI → templated fallback, still contains the full name + topic
    msg, source = await om.generate_thread_ask_message(
        brief="سلام بده", contact=CONTACT, topic="پیگیری سفارش تلویزیون", step_count=0,
        cold_phone_digits=["989120000001"], ai_fn=None, rng=random.Random(1))
    assert source == "fallback"
    assert "رضا محمدی" in msg
    assert "پیگیری سفارش تلویزیون" in msg


@pytest.mark.asyncio
async def test_generated_message_uses_ai_and_profile_line():
    seen = {}
    async def ai(*, name, topic, step_count, brief, profile_line):
        seen["profile_line"] = profile_line
        seen["topic"] = topic
        seen["step_count"] = step_count
        return f"سلام {name}، درباره‌ی {topic} یه لطف کوچیک داشتم"
    msg, source = await om.generate_thread_ask_message(
        brief="سلام بده", contact=CONTACT, topic="پیگیری سفارش تلویزیون", step_count=2,
        cold_phone_digits=["989120000001"], ai_fn=ai, rng=random.Random(1))
    assert source == "ai" and "رضا محمدی" in msg
    # profile info was passed to the model (job/experience/benefit)
    assert "کارشناس فروش" in seen["profile_line"]
    assert "۶ سال" in seen["profile_line"] or "6 سال" in seen["profile_line"]
    assert "تخفیف پرسنلی" in seen["profile_line"]
    assert seen["step_count"] == 2         # thread continuation signalled to the model


@pytest.mark.asyncio
async def test_ai_output_leaking_identifier_falls_back():
    async def ai(*, name, topic, step_count, brief, profile_line):
        return f"سلام {name}، شماره ۹۸۹۱۲۳۴۵۶۷۸۹ رو بگیر"   # long digit run → unsafe
    msg, source = await om.generate_thread_ask_message(
        brief="سلام بده", contact=CONTACT, topic="پیگیری سفارش یخچال", step_count=1,
        cold_phone_digits=["989120000001"], ai_fn=ai, forbidden=("989120000001",),
        rng=random.Random(2))
    assert source == "fallback"          # unsafe AI output rejected
    # the ONLY long digit run in the final message is the wa.me link's own digits
    body = msg.split("\n")[0]
    assert not re.search(r"\d{7,}", body)


# ── ≤ 2 cold accounts, correct wa.me links ───────────────────────────────────
@pytest.mark.asyncio
async def test_two_cold_accounts_two_links():
    msg, _ = await om.generate_thread_ask_message(
        brief=None, contact=CONTACT, topic="پیگیری سفارش کولر", step_count=0,
        cold_phone_digits=["989120000001", "989130000002"], ai_fn=None, rng=random.Random(3))
    assert "https://wa.me/989120000001" in msg
    assert "https://wa.me/989130000002" in msg


@pytest.mark.asyncio
async def test_never_more_than_two_cold_accounts():
    msg, _ = await om.generate_thread_ask_message(
        brief=None, contact=CONTACT, topic="پیگیری سفارش کولر", step_count=0,
        cold_phone_digits=["989120000001", "989130000002", "989140000003"],
        ai_fn=None, rng=random.Random(3))
    links = re.findall(r"https://wa\.me/\d+", msg)
    assert len(links) == 2                         # third assignment never referenced
    assert "989140000003" not in msg


@pytest.mark.asyncio
async def test_name_that_is_identifier_rejected():
    with pytest.raises(ValueError):
        await om.generate_thread_ask_message(
            brief=None, contact={"name": "98912345678"}, topic="x", step_count=0,
            cold_phone_digits=[], ai_fn=None, rng=random.Random(1))
