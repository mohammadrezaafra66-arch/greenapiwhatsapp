"""V40 PART 5 — story-detected products feed the EXISTING report, tagged source='status'.

Proves:
  • a newly-analyzed story with a product writes ONE product_mention_logs row with source='status'
    (and the matched product_id), only on first analysis — a cache hit writes nothing;
  • the shared top-products aggregation surfaces that row and its `sources`, and the منبع filter
    narrows to a single source — existing pv/group rows keep their own source (real-DB integration).
"""
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services.product_reports import _split_sources, top_products_rows


def test_split_sources_dedups_and_sorts():
    assert _split_sources("pv,group,pv,status") == ["group", "pv", "status"]
    assert _split_sources(None) == []
    assert _split_sources("") == []


# ── story analysis writes a source='status' mention (fake session) ────────────────────────────
class _Result:
    def __init__(self, obj): self._obj = obj
    def scalar_one_or_none(self): return self._obj
    def scalars(self): return self
    def all(self): return self._obj if isinstance(self._obj, list) else []


class _DB:
    def __init__(self):
        self.store = {}
        self.added = []
    async def execute(self, q):
        params = q.compile().params
        if "story_id_1" in params:
            return _Result(self.store.get(params["story_id_1"]))
        return _Result([])
    async def get(self, model, pk): return None
    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.added.append(obj)
        if hasattr(obj, "story_id"):
            self.store[obj.story_id] = obj
    async def commit(self): pass


def _story(**kw):
    base = dict(id=uuid.uuid4(), instance_id="inst-1", status_type="text",
                local_media_path=None, text_content="کولر گازی گری 18000 موجود شد",
                caption=None, sender_phone="989121112233", sender_name="فروشگاه پارس")
    base.update(kw)
    return SimpleNamespace(**base)


CATALOG = [{"name": "کولر گازی گری 18000", "id": "cat-1"}]


@pytest.mark.asyncio
async def test_story_detection_writes_status_mention(monkeypatch):
    async def _catalog(*_a, **_k): return CATALOG
    monkeypatch.setattr("app.services.price_service.get_products", _catalog)
    from app.api.v1 import statuses
    from app.models.reporting import ProductMentionLog

    db = _DB()
    story = _story()
    await statuses._analyze_story_rows(db, [story])
    mentions = [o for o in db.added if isinstance(o, ProductMentionLog)]
    assert len(mentions) == 1
    m = mentions[0]
    assert m.source == "status"
    assert m.product_id == "cat-1"
    assert m.sender_phone == "989121112233"
    assert "کولر" in m.product_name


@pytest.mark.asyncio
async def test_cache_hit_writes_no_duplicate_mention(monkeypatch):
    async def _catalog(*_a, **_k): return CATALOG
    monkeypatch.setattr("app.services.price_service.get_products", _catalog)
    from app.api.v1 import statuses
    from app.models.reporting import ProductMentionLog

    db = _DB()
    story = _story()
    await statuses._analyze_story_rows(db, [story])         # first → 1 mention
    await statuses._analyze_story_rows(db, [story])         # cached → no new mention
    mentions = [o for o in db.added if isinstance(o, ProductMentionLog)]
    assert len(mentions) == 1


@pytest.mark.asyncio
async def test_no_product_writes_no_mention(monkeypatch):
    async def _catalog(*_a, **_k): return CATALOG
    monkeypatch.setattr("app.services.price_service.get_products", _catalog)
    from app.api.v1 import statuses
    from app.models.reporting import ProductMentionLog

    db = _DB()
    story = _story(text_content="سلام دوستان روز خوبی داشته باشید")
    await statuses._analyze_story_rows(db, [story])
    assert [o for o in db.added if isinstance(o, ProductMentionLog)] == []


# ── the aggregation applies the source filter and parses the distinct sources ─────────────────
class _AggRow(SimpleNamespace):
    pass


class _CaptureResult:
    def __init__(self, rows): self._rows = rows
    def all(self): return list(self._rows)


class _CaptureDB:
    """Records the executed query so we can assert the source filter is applied, and returns a
    seeded aggregate row so we can assert `sources` parsing."""
    def __init__(self, rows):
        self.rows = rows
        self.last_params = None
    async def execute(self, q):
        self.last_params = q.compile().params
        return _CaptureResult(self.rows)


@pytest.mark.asyncio
async def test_source_filter_binds_the_source_value():
    db = _CaptureDB([])
    await top_products_rows(db, days=30, limit=50, source="status")
    assert "status" in set(db.last_params.values())          # the filter bound source='status'

    db2 = _CaptureDB([])
    await top_products_rows(db2, days=30, limit=50)           # no source → no such bind
    assert "status" not in set(db2.last_params.values())
    assert "pv" not in set(db2.last_params.values())


@pytest.mark.asyncio
async def test_sources_column_parsed_into_list():
    row = _AggRow(product_name="کولر گازی گری 18000", product_id="cat-1", mention_count=5,
                  group_count=2, sender_count=3, sources="pv,status,group", last_mention=datetime(2026, 7, 22))
    db = _CaptureDB([row])
    out = await top_products_rows(db, days=30, limit=50)
    assert out[0]["sources"] == ["group", "pv", "status"]
    assert out[0]["in_assistant"] is True
    assert out[0]["mention_count"] == 5
