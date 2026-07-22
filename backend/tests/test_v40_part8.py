"""V40 PART 8 — end-to-end pipeline: one story flows through every stage.

Simulates the whole feature on one capable fake session:
  story arrives → media persisted locally (PART 1) → analyzed once, cached (PART 2/3) → the detected
  catalog product writes a source='status' mention (PART 5) → that mention feeds the EXISTING
  top-products report (PART 5) and the per-contact trend (PART 6) → and raises a catalog-spotted
  alert because the advertiser is an outside contact (PART 7).
"""
import uuid
from datetime import datetime, date

import pytest

from app.services import story_media
from app.services.story_media import persist_incoming_statuses
from app.models.received_status import ReceivedStatus
from app.models.story_analysis import StoryProductAnalysis
from app.models.reporting import ProductMentionLog
from app.models.catalog_alert import CatalogSpotAlert


CATALOG = [{"name": "کولر گازی گری 18000", "id": "cat-1"}]

IMAGE_STORY = {
    "idMessage": "E2E-1", "chatId": "989121112233@c.us", "senderName": "فروشگاه رقیب",
    "type": "image", "urlFile": "https://api.example/story/E2E-1.jpg",
    "caption": "", "timestamp": 1758537600,
}


class _Result:
    def __init__(self, one=None, rows=None):
        self._one = one
        self._rows = rows or []
    def scalar_one_or_none(self): return self._one
    def first(self): return (self._one,) if self._one is not None else None
    def scalars(self): return self
    def all(self): return list(self._rows)


class _PipelineDB:
    """A fake session capable enough to route every query the pipeline issues, by bound-param shape."""
    def __init__(self):
        self.added = []
        self.commits = 0
    def _of(self, cls): return [o for o in self.added if isinstance(o, cls)]
    async def execute(self, q):
        p = q.compile().params
        if "status_message_id_1" in p and "instance_id_1" in p:
            row = next((r for r in self._of(ReceivedStatus)
                        if r.instance_id == p["instance_id_1"] and r.status_message_id == p["status_message_id_1"]), None)
            return _Result(one=row)
        if "story_id_1" in p:
            row = next((r for r in self._of(StoryProductAnalysis) if str(r.story_id) == str(p["story_id_1"])), None)
            return _Result(one=row)
        if "contact_phone_1" in p:
            row = next((a for a in self._of(CatalogSpotAlert)
                        if a.contact_phone == p["contact_phone_1"] and a.product_name == p["product_name_1"]
                        and a.alert_date == p["alert_date_1"]), None)
            return _Result(one=row)
        return _Result(rows=[])          # Account.phone → no own accounts (advertiser is outside)
    async def get(self, model, pk): return None
    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.added.append(obj)
    async def commit(self): self.commits += 1


async def _fake_downloader(url, dest):
    return 4096                          # pretend we streamed bytes to `dest`


class _Vision:
    async def __call__(self, path):
        return {"text": "کولر گازی گری 18000"}   # vision sees the catalog product


@pytest.mark.asyncio
async def test_full_pipeline_story_to_report_trend_and_alert(monkeypatch, tmp_path):
    monkeypatch.setattr(story_media, "STORY_MEDIA_DIR", str(tmp_path))
    async def _catalog(*_a, **_k): return CATALOG
    monkeypatch.setattr("app.services.price_service.get_products", _catalog)
    from app.api.v1 import statuses
    from app.services import product_reports as pr

    db = _PipelineDB()

    # 1) story arrives → persisted + media downloaded locally (PART 1)
    summary = await persist_incoming_statuses(db, "7105325764", [IMAGE_STORY], downloader=_fake_downloader)
    assert summary == {"persisted": 1, "downloaded": 1, "skipped": 0}
    story = db._of(ReceivedStatus)[0]
    assert story.media_downloaded is True and story.local_media_path.startswith(str(tmp_path))

    # 2/3) analyze once → StoryProductAnalysis (catalog match) (PART 2/3)
    # 5) writes a source='status' ProductMentionLog; 7) raises a spot alert (outside contact)
    results = await statuses._analyze_story_rows(db, [story], vision_fn=_Vision())
    analysis, from_cache = results[0]
    assert from_cache is False
    assert analysis.in_assistant is True and analysis.matched_product_id == "cat-1"

    mentions = db._of(ProductMentionLog)
    assert len(mentions) == 1 and mentions[0].source == "status"
    assert mentions[0].product_id == "cat-1"

    alerts = db._of(CatalogSpotAlert)
    assert len(alerts) == 1
    assert alerts[0].contact_phone == "9121112233" and alerts[0].product_id == "cat-1"

    # re-analyze → cache hit; NO new analysis / mention / alert (cost control + no dup)
    again = await statuses._analyze_story_rows(db, [story], vision_fn=_Vision())
    assert again[0][1] is True
    assert len(db._of(StoryProductAnalysis)) == 1
    assert len(db._of(ProductMentionLog)) == 1
    assert len(db._of(CatalogSpotAlert)) == 1

    # 5) the produced mention feeds the EXISTING top-products report with source='status'
    class _AggDB:
        def __init__(self, rows): self._rows = rows
        async def execute(self, q): return _Result(rows=self._rows)
    from types import SimpleNamespace
    agg_row = SimpleNamespace(product_name="کولر گازی گری 18000", product_id="cat-1",
                              mention_count=1, group_count=0, sender_count=1,
                              sources="status", last_mention=datetime(2026, 7, 22))
    top = await pr.top_products_rows(_AggDB([agg_row]), days=30, limit=50)
    assert top[0]["sources"] == ["status"] and top[0]["in_assistant"] is True

    # 6) and the per-contact trend surfaces it for the advertiser
    trend = await pr.contact_trend_rows(_AggDB([mentions[0]]), phone="09121112233", days=90)
    assert trend["summary"][0]["product_name"] == "کولر گازی گری 18000"
    assert trend["summary"][0]["count"] == 1
    assert trend["timeline"][0]["source"] == "status"
