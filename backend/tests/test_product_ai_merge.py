import json

import pytest

from app.services.product_ai_merge import (
    LLM_ENTRY_LIMIT,
    _payload,
    ai_product_merge_aliases,
    deterministic_model_aliases,
    parse_ai_merge_aliases,
)


def test_parse_ai_merge_aliases_accepts_high_confidence_known_members():
    text = '{"groups":[{"id":"bosch-46nw01","confidence":0.91,"members":["a","b"]}]}'
    assert parse_ai_merge_aliases(text, {"a", "b", "c"}) == {"a": "a", "b": "a"}


def test_parse_ai_merge_aliases_rejects_low_confidence_unknown_and_bad_json():
    assert parse_ai_merge_aliases("not json", {"a", "b"}) == {}
    low = '{"groups":[{"id":"x","confidence":0.5,"members":["a","b"]}]}'
    assert parse_ai_merge_aliases(low, {"a", "b"}) == {}
    below_threshold = '{"groups":[{"id":"x","confidence":0.85,"members":["a","b"]}]}'
    assert parse_ai_merge_aliases(below_threshold, {"a", "b"}) == {}
    unknown = '{"groups":[{"id":"x","confidence":0.95,"members":["a","z"]}]}'
    assert parse_ai_merge_aliases(unknown, {"a", "b"}) == {}


def test_payload_exposes_model_hints_for_short_whatsapp_variants():
    payload = json.loads(_payload([
        {
            "canonical_key": "ماکرو ال جی 8265 سیلور موجود شد",
            "product_name": "ماکرو ال جی 8265 سیلور موجود شد",
            "mention_count": 4,
        },
        {
            "canonical_key": "microwave|مایکروویو|MH8265CIS",
            "product_name": "مایکروویو ال جی مدل MH8265CIS",
            "mention_count": 1,
        },
    ]))
    rows = payload["rows"]
    assert rows[0]["normalized_name"]
    assert "8265" in rows[0]["model_hints"]
    assert "8265" in rows[1]["model_hints"]
    assert rows[1]["category_hint"] == "microwave"


def test_deterministic_model_aliases_merge_short_and_full_model_variants():
    alias = deterministic_model_aliases([
        {
            "canonical_key": "ماکرو ال جی 8265 سیلور موجود شد",
            "product_name": "ماکرو ال جی 8265 سیلور موجود شد",
        },
        {
            "canonical_key": "microwave|مایکروویو|MH8265CIS",
            "product_name": "مایکروویو ال جی مدل MH8265CIS",
        },
        {
            "canonical_key": "💎ماکرو 8265s موجود💎 مایکروویو ال جی",
            "product_name": "💎ماکرو 8265s موجود💎 مایکروویو ال جی",
        },
    ])
    assert set(alias) == {
        "ماکرو ال جی 8265 سیلور موجود شد",
        "microwave|مایکروویو|MH8265CIS",
        "💎ماکرو 8265s موجود💎 مایکروویو ال جی",
    }
    assert len(set(alias.values())) == 1


def test_deterministic_model_aliases_do_not_merge_different_models():
    alias = deterministic_model_aliases([
        {
            "canonical_key": "fridge|ساید|بای|X267",
            "product_name": "یخچال ساید بای ساید ال جی مدل X267 رنگ سیلور",
        },
        {
            "canonical_key": "fridge|ساید|بای|X287",
            "product_name": "یخچال ساید بای ساید ال جی مدل X287 رنگ سیلور",
        },
    ])
    assert alias == {}


@pytest.mark.asyncio
async def test_ai_product_merge_skips_llm_for_large_reports_but_keeps_deterministic_merges(monkeypatch):
    async def fail_chat(*args, **kwargs):
        raise AssertionError("LLM should not be called for large reports")

    import app.services.gpt_service as gpt_service
    monkeypatch.setattr(gpt_service, "_chat", fail_chat)

    entries = [
        {
            "canonical_key": "ماکرو ال جی 8265 سیلور موجود شد",
            "product_name": "ماکرو ال جی 8265 سیلور موجود شد",
        },
        {
            "canonical_key": "microwave|مایکروویو|MH8265CIS",
            "product_name": "مایکروویو ال جی مدل MH8265CIS",
        },
    ]
    entries.extend(
        {"canonical_key": f"product|dummy|{i}", "product_name": f"محصول تست {i}"}
        for i in range(LLM_ENTRY_LIMIT + 1)
    )

    alias = await ai_product_merge_aliases(entries)
    assert alias["ماکرو ال جی 8265 سیلور موجود شد"] == alias["microwave|مایکروویو|MH8265CIS"]
