"""Optional AI-assisted product merge for the top-products report.

The deterministic merge is the source of truth. This module is a second-pass quality layer for
ambiguous rows only, and it is deliberately fail-closed: invalid JSON, low confidence, or provider
errors return no aliases.
"""
from __future__ import annotations

import json
import re
import asyncio

from app.services.product_match import product_group_key


SYSTEM = """You are an expert Persian WhatsApp product-deduplication engine for an appliance seller.
Return ONLY valid JSON:
{"groups":[{"id":"short-stable-id","confidence":0.0-1.0,"members":["canonical_key", "..."]}]}

Goal:
Group report rows that describe the SAME real sellable appliance/product, even when WhatsApp text is
short, noisy, missing brand words, Persian/Arabic digits differ, or wording says only "موجود شد".

Strong merge signals:
- Same model/code/core, including suffix or prefix variants: 8265, 8265s, MH8265CIS, "ماکرو ال جی 8265".
- Same product category + same brand/model family with color/origin/status words changed.
- One row is a short availability phrase for the same model as another row.
- Same capacity/model number where the product type is compatible.

Words that are usually NOT identity:
موجود، موجودی، شد، قیمت، ارسال، رنگ، سفید، سیلور، مشکی، دودی، اصل، ساخت، چین، کره، ترکیه، سری، مدل.

Never merge:
- Different product type/category (تلویزیون vs مایکروفر vs یخچال vs کولر).
- Different model core or capacity when both are meaningful: X267 != X287, 55UA85006 != 65UA85006,
  18000 != 24000, SMS46NW01 != SMS46NI01.
- Generic inventory phrases without a shared distinctive model/code/category.

Output rules:
- Use ONLY canonical_key values from the input rows in members.
- Put every merge group separately; do not include one-member groups.
- Confidence must be >=0.88 for merges based on model/code, >=0.92 for category+brand-only merges.
- If unsure, omit the group.
"""


_DIGIT_TRANS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_CODE_RE = re.compile(r"[A-Z]*\d{3,}[A-Z0-9]*", re.IGNORECASE)
LLM_ENTRY_LIMIT = 120
LLM_TIMEOUT_SECONDS = 5


def _model_hints(name: str, canonical_key: str) -> list[str]:
    raw = f"{name or ''} {canonical_key or ''}".translate(_DIGIT_TRANS).upper()
    hints = []
    for token in _CODE_RE.findall(raw):
        compact = re.sub(r"[^0-9A-Z]", "", token)
        if not compact:
            continue
        hints.append(compact)
        digits = "".join(ch for ch in compact if ch.isdigit())
        if len(digits) >= 3:
            hints.append(digits)
    return sorted(set(hints), key=lambda x: (len(x), x), reverse=True)[:8]


def _category_hint(canonical_key: str) -> str:
    head = (canonical_key or "").split("|", 1)[0]
    known = {"dishwasher", "washing_machine", "vacuum", "fridge", "tv", "air_conditioner", "microwave"}
    return head if head in known else ""


def _root_aliases(members: list[str]) -> dict[str, str]:
    root = sorted(members)[0]
    return {m: root for m in members}


def deterministic_model_aliases(entries: list[dict]) -> dict[str, str]:
    """Merge obvious shared model/code variants before asking AI.

    WhatsApp ads often write only a short numeric/model core ("8265 موجود") while another row carries
    the full catalog-ish model ("MH8265CIS"). When the shared model hint is strong and explicit
    categories do not conflict, this is safer and more reliable than leaving it entirely to the LLM.
    """
    buckets: dict[str, list[dict]] = {}
    for e in entries:
        key = e.get("canonical_key")
        name = e.get("product_name")
        if not key or not name:
            continue
        row = {
            "key": key,
            "category": _category_hint(key),
            "hints": _model_hints(name, key),
        }
        for hint in row["hints"]:
            if len(hint) >= 4:
                buckets.setdefault(hint, []).append(row)

    alias: dict[str, str] = {}
    for rows in buckets.values():
        keys = sorted({r["key"] for r in rows})
        if len(keys) < 2:
            continue
        explicit_categories = {r["category"] for r in rows if r["category"]}
        if len(explicit_categories) > 1:
            continue
        alias.update(_root_aliases(keys))
    return alias


def _payload(entries: list[dict]) -> str:
    rows = [
        {
            "canonical_key": e.get("canonical_key"),
            "name": e.get("product_name"),
            "normalized_name": product_group_key(e.get("product_name") or ""),
            "category_hint": _category_hint(e.get("canonical_key") or ""),
            "model_hints": _model_hints(e.get("product_name") or "", e.get("canonical_key") or ""),
            "count": e.get("mention_count"),
            "in_assistant": bool(e.get("product_id")),
        }
        for e in entries
        if e.get("canonical_key") and e.get("product_name")
    ]
    return json.dumps({"rows": rows}, ensure_ascii=False)


def parse_ai_merge_aliases(text: str, valid_keys: set[str], *, min_confidence: float = 0.88) -> dict[str, str]:
    try:
        data = json.loads(text or "{}")
    except Exception:
        return {}
    alias: dict[str, str] = {}
    for group in data.get("groups") or []:
        try:
            conf = float(group.get("confidence") or 0)
        except Exception:
            conf = 0
        members = [m for m in (group.get("members") or []) if m in valid_keys]
        if conf < min_confidence or len(members) < 2:
            continue
        root = sorted(members)[0]
        for m in members:
            alias[m] = root
    return alias


async def ai_product_merge_aliases(entries: list[dict]) -> dict[str, str]:
    valid = {e.get("canonical_key") for e in entries if e.get("canonical_key")}
    if len(valid) < 2:
        return {}
    deterministic = deterministic_model_aliases(entries)
    if len(valid) > LLM_ENTRY_LIMIT:
        return deterministic
    from app.services.gpt_service import _chat
    try:
        text = await asyncio.wait_for(
            _chat(SYSTEM, _payload(entries), max_tokens=4000, temperature=0.0),
            timeout=LLM_TIMEOUT_SECONDS,
        )
    except Exception as e:
        print(f"[ProductMergeAI] LLM skipped: {e}")
        return deterministic
    return {**parse_ai_merge_aliases(text or "", valid), **deterministic}
