"""V40 PART 2 — story analysis schema + the analyze-once archive.

Proves the hard cost-control rule: analyzing the same story twice calls the analyzer (AI/OCR path)
exactly ONCE — the second call returns the cached archive row — and the persisted row faithfully
carries the analyzer's result.
"""
import uuid
from types import SimpleNamespace

import pytest

from app.services.story_analysis import analyze_story_once, get_cached_analysis
from app.models.story_analysis import StoryProductAnalysis


class _Result:
    def __init__(self, obj): self._obj = obj
    def scalar_one_or_none(self): return self._obj


class _DB:
    def __init__(self):
        self.store = {}      # story_id -> row (simulates the unique story_id)
        self.added = []
    async def execute(self, q):
        params = q.compile().params
        sid = params.get("story_id_1")
        return _Result(self.store.get(sid))
    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.added.append(obj)
        self.store[obj.story_id] = obj


class _Analyzer:
    def __init__(self, result):
        self.result = result
        self.calls = 0
    async def __call__(self, story):
        self.calls += 1
        return self.result


RESULT = {
    "analysis_type": "image", "detected_product_name": "کولر گازی گری ۱۸۰۰۰",
    "matched_product_id": "cat-42", "in_assistant": True, "ai_confidence": 0.83,
    "raw_ai_note": "تصویر یک کولر گازی اسپلیت",
}


@pytest.mark.asyncio
async def test_first_analysis_runs_analyzer_and_persists():
    db = _DB()
    story = SimpleNamespace(id=uuid.uuid4())
    analyzer = _Analyzer(RESULT)
    row, from_cache = await analyze_story_once(db, story, analyzer=analyzer)

    assert from_cache is False and analyzer.calls == 1
    assert row in db.added
    assert row.detected_product_name == "کولر گازی گری ۱۸۰۰۰"
    assert row.matched_product_id == "cat-42"
    assert row.in_assistant is True
    assert abs(row.ai_confidence - 0.83) < 1e-9
    assert row.analysis_type == "image"


@pytest.mark.asyncio
async def test_second_analysis_returns_cache_without_calling_analyzer():
    db = _DB()
    story = SimpleNamespace(id=uuid.uuid4())
    analyzer = _Analyzer(RESULT)

    first, c1 = await analyze_story_once(db, story, analyzer=analyzer)
    second, c2 = await analyze_story_once(db, story, analyzer=analyzer)

    assert c1 is False and c2 is True           # second is a cache hit
    assert analyzer.calls == 1                   # analyzer NOT called the second time
    assert second is first                       # same archived row
    assert len(db.added) == 1


@pytest.mark.asyncio
async def test_get_cached_analysis_none_when_unseen():
    db = _DB()
    story = SimpleNamespace(id=uuid.uuid4())
    assert await get_cached_analysis(db, story.id) is None


@pytest.mark.asyncio
async def test_non_product_result_still_cached_no_reanalyze():
    """A story with NO product found is still archived, so it is never re-analyzed (no wasted AI)."""
    db = _DB()
    story = SimpleNamespace(id=uuid.uuid4())
    analyzer = _Analyzer({"analysis_type": "text", "in_assistant": False})
    row, c1 = await analyze_story_once(db, story, analyzer=analyzer)
    _, c2 = await analyze_story_once(db, story, analyzer=analyzer)

    assert c1 is False and c2 is True
    assert analyzer.calls == 1
    assert row.detected_product_name is None and row.in_assistant is False
