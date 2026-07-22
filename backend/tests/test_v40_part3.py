"""V40 PART 3 — text + image story analysis, reusing the existing detector; manual + bulk triggers.

Proves:
  • a TEXT story is matched with the SAME detect_product_mentions() used for PV/group (catalog hit,
    non-catalog commerce line, and plain chat → no product);
  • an IMAGE story is analyzed via the injected vision path, then matched with that same detector;
    an unmatched vision description is still recorded as an outside-assistant sighting;
  • an "image" status with no persisted local media is treated as text (no vision call);
  • the shared analysis path analyzes each story once and, on re-run, serves the PART 2 cache
    (never re-invoking vision); the bulk summary counts products / outside-assistant correctly.
"""
import uuid
from types import SimpleNamespace

import pytest

from app.services.story_analyzer import build_story_analyzer


@pytest.fixture(autouse=True)
def _no_spot_alert(monkeypatch):
    """PART 7's spot-alert path queries Account/CatalogSpotAlert — orthogonal to PART 3's analysis;
    stub it so these lightweight fake sessions aren't required to model those queries."""
    async def _cores(*_a, **_k): return set()
    async def _raise(*_a, **_k): return False
    monkeypatch.setattr("app.services.catalog_spot_alert.get_our_phone_cores", _cores)
    monkeypatch.setattr("app.services.catalog_spot_alert.maybe_raise_spot_alert", _raise)
    yield


CATALOG = [{"name": "کولر گازی گری 18000", "id": "cat-1"}]


def _story(**kw):
    base = dict(id=uuid.uuid4(), status_type="text", local_media_path=None,
                text_content=None, caption=None, sender_phone="989120000000",
                sender_name="فروشنده", instance_id="inst-1")
    base.update(kw)
    return SimpleNamespace(**base)


class _Vision:
    def __init__(self, text):
        self.text = text
        self.calls = 0
    async def __call__(self, path):
        self.calls += 1
        return {"text": self.text} if self.text else None


@pytest.mark.asyncio
async def test_text_story_matches_catalog():
    analyzer = build_story_analyzer(CATALOG, vision_fn=_Vision(None))
    r = await analyzer(_story(text_content="کولر گازی گری 18000 موجود شد، تماس بگیرید"))
    assert r["analysis_type"] == "text"
    assert r["in_assistant"] is True
    assert r["matched_product_id"] == "cat-1"
    assert "کولر" in r["detected_product_name"]


@pytest.mark.asyncio
async def test_text_story_unknown_commerce_line_is_outside_assistant():
    v = _Vision(None)
    analyzer = build_story_analyzer(CATALOG, vision_fn=v)
    r = await analyzer(_story(text_content="یخچال ساید بای ساید سامسونگ درجه یک، قیمت 25 میلیون تومان"))
    assert r["in_assistant"] is False
    assert r["detected_product_name"] and "یخچال" in r["detected_product_name"]
    assert r["matched_product_id"] is None
    assert v.calls == 0                      # text story never calls vision


@pytest.mark.asyncio
async def test_plain_chat_text_finds_no_product():
    analyzer = build_story_analyzer(CATALOG, vision_fn=_Vision(None))
    r = await analyzer(_story(text_content="سلام خوبی؟ ممنون از پیگیریت"))
    assert r["detected_product_name"] is None and r["in_assistant"] is False


@pytest.mark.asyncio
async def test_image_story_uses_vision_and_matches_catalog():
    v = _Vision("کولر گازی گری 18000")
    analyzer = build_story_analyzer(CATALOG, vision_fn=v)
    r = await analyzer(_story(status_type="image", local_media_path="/x/img.jpg"))
    assert v.calls == 1
    assert r["analysis_type"] == "image"
    assert r["in_assistant"] is True and r["matched_product_id"] == "cat-1"
    assert r["raw_ai_note"] == "کولر گازی گری 18000"


@pytest.mark.asyncio
async def test_image_vision_unmatched_keeps_description_outside():
    v = _Vision("کفش ورزشی نایک اورجینال")
    analyzer = build_story_analyzer(CATALOG, vision_fn=v)
    r = await analyzer(_story(status_type="image", local_media_path="/x/img.jpg"))
    assert r["analysis_type"] == "image"
    assert r["in_assistant"] is False
    assert r["detected_product_name"] == "کفش ورزشی نایک اورجینال"


@pytest.mark.asyncio
async def test_image_without_local_media_is_text_and_skips_vision():
    v = _Vision("something")
    analyzer = build_story_analyzer(CATALOG, vision_fn=v)
    r = await analyzer(_story(status_type="image", local_media_path=None,
                              text_content="کولر گازی گری 18000 موجود"))
    assert v.calls == 0
    assert r["analysis_type"] == "text" and r["in_assistant"] is True


@pytest.mark.asyncio
async def test_image_caption_combines_with_vision():
    v = _Vision("تصویر یک محصول")
    analyzer = build_story_analyzer(CATALOG, vision_fn=v)
    # caption carries the catalog product; vision text is generic — combined still matches.
    r = await analyzer(_story(status_type="image", local_media_path="/x/i.jpg",
                              caption="کولر گازی گری 18000"))
    assert r["in_assistant"] is True and r["matched_product_id"] == "cat-1"


# ── shared analysis path: analyze-once + cache reuse across the bulk run ───────────────────────
class _Result:
    def __init__(self, obj): self._obj = obj
    def scalar_one_or_none(self): return self._obj
    def scalars(self): return self
    def all(self): return self._obj if isinstance(self._obj, list) else []


class _DB:
    def __init__(self, fetch_rows=None):
        self.store = {}
        self.added = []
        self.commits = 0
        self._fetch_rows = fetch_rows or []
    async def execute(self, q):
        params = q.compile().params
        if "story_id_1" in params:                      # per-story cache check
            return _Result(self.store.get(params["story_id_1"]))
        return _Result(list(self._fetch_rows))          # bulk today-unanalyzed fetch
    async def get(self, model, pk): return None
    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.added.append(obj)
        if hasattr(obj, "story_id"):          # StoryProductAnalysis (not the ProductMentionLog)
            self.store[obj.story_id] = obj
    async def commit(self): self.commits += 1


@pytest.mark.asyncio
async def test_analyze_rows_analyzes_once_then_caches(monkeypatch):
    async def _catalog(*_a, **_k):
        return CATALOG
    monkeypatch.setattr("app.services.price_service.get_products", _catalog)
    from app.api.v1 import statuses
    v = _Vision("کولر گازی گری 18000")
    story = _story(status_type="image", local_media_path="/x/i.jpg")
    db = _DB()

    first = await statuses._analyze_story_rows(db, [story], vision_fn=v)
    assert first[0][1] is False and v.calls == 1
    # Re-run the SAME story → served from the archive, vision NOT called again.
    second = await statuses._analyze_story_rows(db, [story], vision_fn=v)
    assert second[0][1] is True and v.calls == 1
    from app.models.story_analysis import StoryProductAnalysis
    analyses = [o for o in db.added if isinstance(o, StoryProductAnalysis)]
    assert len(analyses) == 1                 # analyzed once; the cache hit added no second analysis


@pytest.mark.asyncio
async def test_bulk_summary_counts(monkeypatch):
    async def _catalog(*_a, **_k):
        return CATALOG
    monkeypatch.setattr("app.services.price_service.get_products", _catalog)
    from app.api.v1 import statuses
    rows = [
        _story(text_content="کولر گازی گری 18000 موجود"),                       # in-assistant
        _story(text_content="یخچال ساید سامسونگ، قیمت 25 میلیون تومان"),        # outside
        _story(text_content="سلام دوستان، روز خوبی داشته باشید"),               # no product
    ]
    db = _DB(fetch_rows=rows)
    out = await statuses.analyze_today_statuses(account_id=None, db=db)
    assert out["analyzed"] == 3
    assert out["products_found"] == 2
    assert out["outside_assistant"] == 1
    assert db.commits == 1
