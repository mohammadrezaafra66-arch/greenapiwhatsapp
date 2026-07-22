"""V40 PART 3 — the real story analyzer (text via the existing detector, image via vision).

Builds the `analyzer(story)` callable that V40 PART 2's analyze_story_once caches. It NEVER
reimplements product matching: text (and any vision-extracted description) is run through the SAME
detect_product_mentions() the PV/group webhook path uses, so catalog matching + non-catalog
extraction + the in_assistant flag are identical across every source.

  • text story  → match on text_content + caption.
  • image story → vision-extract a product description from the persisted LOCAL image (PART 1),
                  combine with any caption, then match with the same detector.

The vision function is injected (default: story_vision.extract_product_from_image) so tests stay
hermetic and never hit a live model.
"""
from __future__ import annotations
import logging

logger = logging.getLogger("afrakala.story_analyzer")

_MAX_NOTE = 180


def _short(text: str | None) -> str | None:
    if not text:
        return None
    t = " ".join(str(text).split())
    return t[:_MAX_NOTE] if t else None


def _caption_text(story) -> str:
    parts = [getattr(story, "text_content", None), getattr(story, "caption", None)]
    return " ".join(p for p in parts if p).strip()


def _is_image_story(story) -> bool:
    return (getattr(story, "status_type", None) == "image") and bool(getattr(story, "local_media_path", None))


async def _default_vision(image_path: str):
    from app.services.story_vision import extract_product_from_image
    return await extract_product_from_image(image_path)


def build_story_analyzer(products: list, *, vision_fn=None):
    """Return an async analyzer(story) → result dict, bound to a product catalog + vision fn."""
    vision_fn = vision_fn or _default_vision

    async def analyzer(story) -> dict:
        from app.services.product_match import detect_product_mentions
        is_image = _is_image_story(story)
        analysis_type = "image" if is_image else "text"
        caption = _caption_text(story)

        vision_text = None
        vision_note = None
        if is_image:
            try:
                v = await vision_fn(story.local_media_path)
            except Exception as e:
                logger.warning("story vision failed (%s): %s", getattr(story, "id", "?"), e)
                v = None
            if isinstance(v, dict):
                vision_text = v.get("text")
            elif isinstance(v, str):
                vision_text = v
            vision_note = _short(vision_text)

        combined = " ".join(p for p in (caption, vision_text) if p).strip()
        hits = detect_product_mentions(combined, products) if combined else []

        detected = matched_id = None
        in_assistant = False
        if hits:
            h = hits[0]
            detected = h.get("product_name")
            matched_id = h.get("product_id")
            in_assistant = bool(h.get("in_assistant"))
        elif vision_text:
            # Vision saw a product the detector could not tie to the catalog nor confidently extract
            # as a commerce line — still record what the model saw, as an outside-assistant sighting.
            detected = _short(vision_text)
            in_assistant = False

        return {
            "analysis_type": analysis_type,
            "detected_product_name": detected,
            "matched_product_id": matched_id,
            "in_assistant": in_assistant,
            "ai_confidence": None,   # chat/vision endpoints don't return a numeric confidence
            "raw_ai_note": vision_note,
        }

    return analyzer
