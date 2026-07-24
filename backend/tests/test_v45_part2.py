"""V45 PART 2 — the own-number exclusion is wired BEFORE any AI/detector call, for every source.

Coverage:
  • STORY/vision path (hermetic, call-count spy): an excluded story never reaches the vision fn and
    persists no story_product_analysis / product_mention row; a normal story is analyzed as before.
  • report safety net: exclude_own_condition builds a null-safe NOT-LIKE predicate; and (real DB) a
    pre-existing own-number mention row is filtered out of top_products_rows.
  • MESSAGE path (real DB, spy): a message from an excluded number never calls detect_product_mentions
    and writes no ProductMentionLog; a normal number behaves exactly as before.
"""
import uuid
from types import SimpleNamespace
from datetime import datetime, timedelta

import pytest

from app.services.own_number_exclusion import normalize_own_number
from app.services.product_reports import exclude_own_condition, top_products_rows


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2.2 — STORY / vision path: ZERO AI calls for an excluded number (hermetic, spy)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class _Res:
    def __init__(self, rows): self._rows = list(rows)
    def scalars(self): return self
    def all(self): return list(self._rows)
    def scalar_one_or_none(self): return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self): self.added = []
    async def execute(self, q): return _Res([])          # story never cached → analyzer would run
    def add(self, o): self.added.append(o)
    async def get(self, *a): return None
    async def commit(self): pass


def _story(phone, mid_path):
    return SimpleNamespace(
        id=uuid.uuid4(), sender_phone=phone, sender_name="S", instance_id="inst",
        status_type="image", local_media_path=mid_path, media_downloaded=True,
        text_content=None, caption=None,
    )


@pytest.mark.asyncio
async def test_excluded_story_never_calls_vision(monkeypatch):
    from app.api.v1 import statuses as st

    async def _cores(_db): return {normalize_own_number("989121111111")}
    async def _our(_db): return set()
    async def _products(_n): return []
    monkeypatch.setattr("app.services.own_number_exclusion.get_excluded_cores", _cores)
    monkeypatch.setattr("app.services.catalog_spot_alert.get_our_phone_cores", _our)
    monkeypatch.setattr("app.services.price_service.get_products", _products)

    vision_calls = []
    async def vision_spy(path):
        vision_calls.append(path)
        return {"text": "some gadget"}

    excluded = _story("989121111111", "/excluded.jpg")   # own number
    normal = _story("989129999999", "/normal.jpg")       # outside number
    db = _FakeDB()
    results = await st._analyze_story_rows(db, [excluded, normal], vision_fn=vision_spy)

    # The costly vision fn ran for the normal story ONLY — the excluded story never reached it.
    assert vision_calls == ["/normal.jpg"]
    assert len(results) == 1
    # No story_product_analysis nor product_mention row was persisted for the excluded number.
    from app.models.story_analysis import StoryProductAnalysis
    from app.models.reporting import ProductMentionLog
    analyses = [o for o in db.added if isinstance(o, StoryProductAnalysis)]
    mentions = [o for o in db.added if isinstance(o, ProductMentionLog)]
    assert all(a.story_id != excluded.id for a in analyses)
    assert all(m.sender_phone == "989129999999" for m in mentions)


@pytest.mark.asyncio
async def test_all_excluded_means_no_vision_at_all(monkeypatch):
    from app.api.v1 import statuses as st

    async def _cores(_db): return {normalize_own_number("989121111111")}
    async def _our(_db): return set()
    async def _products(_n): return []
    monkeypatch.setattr("app.services.own_number_exclusion.get_excluded_cores", _cores)
    monkeypatch.setattr("app.services.catalog_spot_alert.get_our_phone_cores", _our)
    monkeypatch.setattr("app.services.price_service.get_products", _products)

    vision_calls = []
    async def vision_spy(path):
        vision_calls.append(path); return {"text": "x"}

    db = _FakeDB()
    results = await st._analyze_story_rows(
        db, [_story("989121111111", "/a.jpg"), _story("00989121111111", "/b.jpg")],
        vision_fn=vision_spy)
    assert vision_calls == [] and results == []          # zero AI calls, nothing persisted
    assert db.added == []


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2.3 — report safety net: the exclusion predicate
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_exclude_condition_none_when_no_cores():
    assert exclude_own_condition(set()) is None
    assert exclude_own_condition(None) is None
    assert exclude_own_condition({""}) is None


def test_exclude_condition_is_nullsafe_notlike():
    cond = exclude_own_condition({"9121111111"})
    sql = str(cond.compile(compile_kwargs={"literal_binds": True})).upper()
    assert "9121111111" in sql and "NOT LIKE" in sql and "IS NULL" in sql


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2.1 — MESSAGE path (PV/group): gated BEFORE detect_product_mentions (hermetic, fake session + spy)
# ══════════════════════════════════════════════════════════════════════════════════════════════
TEST_INSTANCE = "v45p2_test_inst"
OWN_PHONE = "989121110001"        # listed as own → excluded
OUT_PHONE = "989129990002"        # outside number → detected & counted
OWN_CORE = normalize_own_number(OWN_PHONE)
OUT_CORE = normalize_own_number(OUT_PHONE)


class FakeWebhookSession:
    """Stands in for AsyncSessionLocal() in handle_incoming: returns None for account/entity lookups,
    the configured own-number cores for the exclusion query, and [] for the our-cores query; collects
    every added row into a shared sink so the test can assert what was (not) written."""
    def __init__(self, cores, sink):
        self.cores, self.sink = cores, sink
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def execute(self, q):
        try:
            cds = q.column_descriptions
        except Exception:
            return _Res([])
        if len(cds) == 1:
            nm = cds[0].get("name")
            if nm == "phone_core":          # get_excluded_cores → our own numbers
                return _Res(list(self.cores))
            if nm == "phone":               # get_our_phone_cores → Account.phone
                return _Res([])
        return _Res([])                     # Account / CampaignContact entity selects → None
    def add(self, o): self.sink.append(o)
    async def get(self, *a): return None
    async def commit(self): pass
    async def rollback(self): pass
    async def refresh(self, o): pass


def _stub(monkeypatch, cores, sink):
    """Isolate the product-mention gate: neutralize unrelated best-effort branches, spy on the
    detector, and swap the webhook's session factory for the fake. Returns the detector call log."""
    async def _categorize(_t): return "other"
    async def _helper(*a, **k): return None
    async def _products(_n): return [{"id": None, "name": "لپ‌تاپ"}]
    calls = []
    def _detect_spy(text, products, **k):
        calls.append(text)
        return [{"product_name": "لپ‌تاپ", "product_id": None, "in_assistant": False}]
    monkeypatch.setattr("app.services.gpt_service.categorize_message", _categorize)
    monkeypatch.setattr("app.services.warmup_helper_engine.handle_helper_incoming", _helper)
    monkeypatch.setattr("app.services.price_service.get_products", _products)
    monkeypatch.setattr("app.services.product_match.detect_product_mentions", _detect_spy)
    monkeypatch.setattr("app.api.v1.webhook.AsyncSessionLocal", lambda: FakeWebhookSession(cores, sink))
    return calls


def _payload(phone, text, mid, *, chat_suffix="@c.us"):
    cid = f"{phone}{chat_suffix}"
    return {
        "typeWebhook": "incomingMessageReceived", "idMessage": mid, "timestamp": 1700000000,
        "senderData": {"chatId": cid, "sender": f"{phone}@c.us", "senderName": "Tester", "chatName": "G"},
        "messageData": {"typeMessage": "textMessage", "textMessageData": {"textMessage": text}},
        "instanceData": {"typeInstance": "whatsapp"},
    }


@pytest.mark.asyncio
async def test_message_from_excluded_number_zero_detection(monkeypatch):
    from app.api.v1.webhook import handle_incoming
    from app.models.reporting import ProductMentionLog
    sink = []
    calls = _stub(monkeypatch, {OWN_CORE}, sink)
    await handle_incoming(TEST_INSTANCE, _payload(OWN_PHONE, "لپ‌تاپ ایسوس", "m_own"))
    assert calls == []                                                    # detector NEVER called
    assert [o for o in sink if isinstance(o, ProductMentionLog)] == []    # no mention row written


@pytest.mark.asyncio
async def test_message_from_outside_number_detected_as_before(monkeypatch):
    from app.api.v1.webhook import handle_incoming
    from app.models.reporting import ProductMentionLog
    sink = []
    calls = _stub(monkeypatch, set(), sink)          # nothing excluded
    await handle_incoming(TEST_INSTANCE, _payload(OUT_PHONE, "لپ‌تاپ ایسوس", "m_out"))
    assert calls == ["لپ‌تاپ ایسوس"]                 # detection ran exactly as before
    ml = [o for o in sink if isinstance(o, ProductMentionLog)]
    assert len(ml) == 1 and ml[0].sender_phone == OUT_PHONE and ml[0].source == "pv"


@pytest.mark.asyncio
async def test_group_message_from_excluded_number_also_gated(monkeypatch):
    """The gate is source-agnostic: a GROUP message from an own number is skipped too."""
    from app.api.v1.webhook import handle_incoming
    from app.models.reporting import ProductMentionLog
    sink = []
    calls = _stub(monkeypatch, {OWN_CORE}, sink)
    await handle_incoming(TEST_INSTANCE, _payload(OWN_PHONE, "لپ‌تاپ", "m_grp", chat_suffix="@g.us"))
    assert calls == []
    assert [o for o in sink if isinstance(o, ProductMentionLog)] == []


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2.3 — report safety net end-to-end (real DB): a pre-existing own-number row is filtered out
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_report_filters_preexisting_own_number_rows():
    """A legacy mention row from an own number is kept OUT of the top-products report by the
    exclude_cores safety net, while the same product from an outside number is still counted."""
    from app.database import AsyncSessionLocal, engine
    from app.models.reporting import ProductMentionLog
    from sqlalchemy import delete
    await engine.dispose()          # fresh, loop-bound pool → avoid a stale cross-test connection
    prod = "V45TESTPROD یخچال دوقلو"
    now = datetime.utcnow()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(ProductMentionLog).where(ProductMentionLog.product_name == prod))
        db.add(ProductMentionLog(product_name=prod, source="group", sender_phone=OWN_PHONE,
                                 instance_id=TEST_INSTANCE, mentioned_at=now))
        db.add(ProductMentionLog(product_name=prod, source="group", sender_phone=OUT_PHONE,
                                 instance_id=TEST_INSTANCE, mentioned_at=now))
        await db.commit()
    try:
        async with AsyncSessionLocal() as db:
            base = await top_products_rows(db, days=2, limit=1000)              # no exclusion → both
            b = next((r for r in base if r["product_name"] == prod), None)
            assert b is not None and b["mention_count"] == 2
            filt = await top_products_rows(db, days=2, limit=1000, exclude_cores={OWN_CORE})
            f = next((r for r in filt if r["product_name"] == prod), None)
            assert f is not None and f["mention_count"] == 1 and f["sender_count"] == 1
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(ProductMentionLog).where(ProductMentionLog.product_name == prod))
            await db.commit()
