"""V23 — the multi-provider AI key pool is wired into mesh warm-up as the PRIMARY
content source, with the curated Persian phrase pool as fallback only on AI failure.

These tests inject a fake chat layer (no network) to prove: AI is called first, its
output is cleaned, and the generator degrades to the phrase pool when AI raises/returns
empty. A source-inspection guard proves the beat task actually passes the ai_fn.
"""
import inspect
import random
import pytest

from app.services.warmup_ai import build_warmup_ai_fn, persona_for_instance, _clean
from app.services.warmup_content import generate_mesh_message


@pytest.mark.asyncio
async def test_ai_is_called_first_and_used():
    calls = []

    async def fake_chat(system, user, max_tokens, temperature):
        calls.append((system, user, max_tokens, temperature))
        return "قیمت پکیج دیواری امروز چطوره؟"

    ai_fn = build_warmup_ai_fn(chat_fn=fake_chat)
    # V24: names must be realistic curated first names — never account labels. "رضا"
    # is in the safe pool, so it reaches the prompt; a label/number would be dropped.
    text, source = await generate_mesh_message(ai_fn=ai_fn, name="رضا", rng=random.Random(1))

    assert source == "ai"
    assert text == "قیمت پکیج دیواری امروز چطوره؟"
    assert len(calls) == 1                                   # AI attempted first
    system, user, max_tokens, _temp = calls[0]
    assert "لوازم خانگی" in system                           # persona system prompt
    assert "رضا" in user                                     # recipient name fed in
    assert max_tokens <= 100                                 # kept short


@pytest.mark.asyncio
async def test_history_is_fed_into_prompt():
    seen = {}

    async def fake_chat(system, user, max_tokens, temperature):
        seen["user"] = user
        return "بله موجوده، فردا می‌فرستم 👍"

    ai_fn = build_warmup_ai_fn(chat_fn=fake_chat)
    await generate_mesh_message(ai_fn=ai_fn, history=["سلام قیمت یخچال ساید؟"],
                                name="رضا", rng=random.Random(1))
    assert "سلام قیمت یخچال ساید؟" in seen["user"]           # running history included


@pytest.mark.asyncio
async def test_falls_back_only_when_ai_raises():
    async def boom(system, user, max_tokens, temperature):
        raise RuntimeError("all providers down / over budget")

    ai_fn = build_warmup_ai_fn(chat_fn=boom)
    text, source = await generate_mesh_message(ai_fn=ai_fn, rng=random.Random(2))
    assert source == "fallback" and text.strip()


@pytest.mark.asyncio
async def test_falls_back_when_ai_returns_empty():
    async def empty(system, user, max_tokens, temperature):
        return None

    ai_fn = build_warmup_ai_fn(chat_fn=empty)
    text, source = await generate_mesh_message(ai_fn=ai_fn, rng=random.Random(3))
    assert source == "fallback"


@pytest.mark.asyncio
async def test_ai_output_is_cleaned():
    async def messy(system, user, max_tokens, temperature):
        return '  «سلام قیمت یخچال؟»\nخط اضافه که باید حذف شود '

    ai_fn = build_warmup_ai_fn(chat_fn=messy)
    text, source = await generate_mesh_message(ai_fn=ai_fn, rng=random.Random(4))
    assert source == "ai"
    assert "\n" not in text and not text.startswith("«")
    assert text == "سلام قیمت یخچال؟"


def test_clean_helpers():
    assert _clean("") is None
    assert _clean("  یک خط\nدو خط ") == "یک خط"
    assert _clean('"نقل‌قول"') == "نقل‌قول"
    assert len(_clean("x" * 500)) <= 160


def test_persona_is_stable_per_instance():
    a = persona_for_instance("770022682898")
    b = persona_for_instance("770022682898")
    c = persona_for_instance("7105325764")
    assert a == b and isinstance(a, str) and a
    # different numbers may map to different personas (not guaranteed, but valid strings)
    assert isinstance(c, str) and c


def test_beat_task_passes_ai_fn():
    """Guard: the automatic tick must inject the AI generator (regression against the
    pre-V23 state where ai_fn was never connected → 100% fallback)."""
    from app.workers import tasks
    src = inspect.getsource(tasks.task_process_mesh_warmup)
    assert "build_warmup_ai_fn" in src
    assert "ai_fn=" in src
