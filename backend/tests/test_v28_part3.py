"""V28 PART 3 — AI-personalized per-contact outreach messages from a one-line brief.

Proves:
  • 10 different contacts each get a message containing THEIR own real name;
  • none contain an account number / instance id / system label (V24 hard filter);
  • no two batch messages are near-duplicate (anti-repeat);
  • the wa.me link matches the correct cold number;
  • a missing-name AI result triggers ONE regeneration, then a safe templated fallback that
    still includes the name — never a send with no name;
  • names not in the curated mesh pool are preserved verbatim (real names, not coerced).
"""
import random
import pytest

from app.services import outreach_message as om
from app.services.outreach_message import (
    generate_outreach_message, generate_outreach_batch, message_includes_name,
    build_outreach_fallback, build_outreach_ai_fn,
)
from app.services.warmup_content import looks_like_identifier

COLD_DIGITS = "989048249526"
COLD_LINK = f"https://wa.me/{COLD_DIGITS}"

# real names — deliberately including several NOT in the mesh HUMAN_NAMES pool
NAMES = ["رضا", "بهروز", "ناهید", "جمشید", "کتایون", "اردشیر", "شقایق", "فرزانه", "یاسمن", "بهرام"]


# 10 genuinely-distinct skeletons so a well-behaved AI varies per contact (like temp 0.9 would)
_TEMPLATES = [
    "سلام {name} عزیز، حالت چطوره؟ یه خواهش کوچیک ازت داشتم.",
    "{name} جان درود، امیدوارم روزت عالی باشه — یه کمک کوچیک لازم دارم.",
    "وقت بخیر {name}، ببخش که مزاحم شدم، یه لطف ازت می‌خوام.",
    "{name} سلام، دلم برات تنگ شده بود؛ یه زحمت کوتاه برات دارم.",
    "درود {name}، خوبی رفیق؟ یه کار کوچیک ازت برمیاد.",
    "{name} عزیزم سلام، امیدوارم سرحال باشی، یه درخواست کوچیک دارم.",
    "سلام {name}، چه خبرا از روزگار؟ یه کمک کوچولو می‌خواستم.",
    "{name} جان وقتت بخیر، یه لطفی در حقم می‌کنی؟",
    "های {name}، امیدوارم اوضاعت روبه‌راه باشه، یه چیز کوچیک ازت می‌خوام.",
    "{name} سلام و ارادت، یه زحمت خیلی کوتاه برات دارم اگه میشه.",
]


async def _ai_ok(*, brief, name):
    """A well-behaved AI: greets by real name with genuinely varied wording, no identifiers."""
    idx = sum(ord(c) for c in name) % len(_TEMPLATES)
    return _TEMPLATES[idx].replace("{name}", name)


@pytest.mark.asyncio
async def test_each_contact_message_contains_its_own_name_and_none_are_dupes():
    contacts = [{"name": n, "phone": f"98910000{i:04d}"} for i, n in enumerate(NAMES)]
    results = await generate_outreach_batch(
        brief="به شماره‌های جدید ما سلام بده", contacts=contacts,
        cold_phone_digits=COLD_DIGITS, ai_fn=_ai_ok, rng=random.Random(1))
    assert len(results) == 10
    from app.services.warmup_content import is_near_duplicate
    bodies = []
    for r, n in zip(results, NAMES):
        assert n in r["message"], f"message for {n} missing the name"
        body = r["message"].split("\n")[0]
        assert not is_near_duplicate(body, bodies), f"near-duplicate body for {n}"
        bodies.append(body)
    assert any(r["source"] == "ai" for r in results)   # AI path genuinely exercised


@pytest.mark.asyncio
async def test_no_identifier_leak_in_any_message():
    # forbidden = the sender/cold account identifiers + labels (V24-style)
    forbidden = ("770022683809", "9048249526 گوشی زینب شخصی", "770022682898")

    async def _ai_tries_to_leak(*, brief, name):
        # adversarial: the model tries to include the cold number + a label
        return f"سلام {name}، لطفا به شماره 989048249526 گوشی زینب شخصی پیام بده"

    contacts = [{"name": n, "phone": "9891"} for n in NAMES[:5]]
    results = await generate_outreach_batch(
        brief="سلام کن", contacts=contacts, cold_phone_digits=COLD_DIGITS,
        ai_fn=_ai_tries_to_leak, forbidden=forbidden, rng=random.Random(2))
    for r in results:
        # the leaking AI body is rejected → safe templated fallback (still has the name)
        assert r["source"] == "fallback"
        body = r["message"].split("\n")[0]        # body line only (link line is separate)
        assert not looks_like_identifier(body)    # no 7+ digit run in the body
        assert "زینب" not in body                 # the label never surfaced
        assert r["contact"]["name"] in body       # name still present


@pytest.mark.asyncio
async def test_messages_are_not_near_duplicates():
    # an AI that returns the SAME text regardless of name would be caught by anti-repeat
    same = "سلام {name}، حالت خوبه؟ یه لطف کوچیک داشتم"

    async def _ai_same(*, brief, name):
        return same.replace("{name}", name)
    contacts = [{"name": n, "phone": "9891"} for n in ["رضا", "علی"]]
    results = await generate_outreach_batch(
        brief="x", contacts=contacts, cold_phone_digits=COLD_DIGITS, ai_fn=_ai_same,
        rng=random.Random(3))
    bodies = [r["message"].split("\n")[0] for r in results]
    from app.services.warmup_content import is_near_duplicate
    assert not is_near_duplicate(bodies[1], [bodies[0]])   # second differs from first


@pytest.mark.asyncio
async def test_wa_me_link_matches_cold_number():
    msg, _ = await generate_outreach_message(
        brief="سلام کن", contact_name="رضا", cold_phone_digits=COLD_DIGITS, ai_fn=_ai_ok,
        rng=random.Random(4))
    assert COLD_LINK in msg


@pytest.mark.asyncio
async def test_missing_name_triggers_regeneration_then_fallback():
    calls = {"n": 0}

    async def _ai_forgets_name(*, brief, name):
        calls["n"] += 1
        return "سلام دوست عزیز، یه لطف کوچیک داشتم"   # NO name → invalid every time
    msg, source = await generate_outreach_message(
        brief="سلام کن", contact_name="بهروز", cold_phone_digits=COLD_DIGITS,
        ai_fn=_ai_forgets_name, rng=random.Random(5))
    assert calls["n"] == 2                     # one attempt + one regeneration
    assert source == "fallback"
    assert "بهروز" in msg                       # fallback STILL includes the real name
    assert message_includes_name(msg.split("\n")[0], "بهروز")


@pytest.mark.asyncio
async def test_real_name_not_in_pool_is_preserved():
    # "بهروز" is NOT in the mesh HUMAN_NAMES pool — must still appear (not coerced/dropped)
    msg, source = await generate_outreach_message(
        brief="x", contact_name="بهروز", cold_phone_digits=COLD_DIGITS, ai_fn=_ai_ok,
        rng=random.Random(6))
    assert "بهروز" in msg


def test_fallback_always_contains_name():
    for n in NAMES:
        assert n in build_outreach_fallback(n, random.Random(7))


@pytest.mark.asyncio
async def test_name_that_looks_like_identifier_is_rejected():
    with pytest.raises(ValueError):
        await generate_outreach_message(
            brief="x", contact_name="09121234567", cold_phone_digits=COLD_DIGITS,
            ai_fn=_ai_ok)
