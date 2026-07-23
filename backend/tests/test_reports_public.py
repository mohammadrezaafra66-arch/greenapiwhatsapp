"""Public read-only LAN reports API (/api/v1/reports/*) — proves it can never drift from the
«جدول محصولات پر تکرار» tab and its «مشاهده فروشندگان اخیر» drill-down.

Both the existing UI endpoints and the new public endpoints format from the SAME shared
aggregation (app.services.product_reports), so these tests feed one fake DB through BOTH and assert
the public payload carries exactly the same product/mentioner data the UI endpoint produces (a
strict superset with machine-readable ISO timestamps). Also unit-tests the scoped, env-configurable
CORS allowlist.
"""
import uuid
from datetime import datetime
from types import SimpleNamespace
import pytest

from app.api.v1 import reporting as ui
from app.api.v1 import reports_public as pub
from app.services import product_reports as prs
from app.utils.shamsi import to_shamsi


@pytest.fixture(autouse=True)
def _stub_catalog(monkeypatch):
    """The report endpoints join in the product catalog (price_service.get_products) to tag each
    row with in_assistant/product_id. That call reaches Redis/Supabase, which is neither available
    nor relevant here — stub it to an empty catalog so these tests stay hermetic (no live Redis
    connection lingering into loop teardown). product_id already flows from the DB rows themselves."""
    async def _empty(*_a, **_k):
        return []
    monkeypatch.setattr("app.services.price_service.get_products", _empty)
    yield


# ── fake DB that returns seeded rows for the two query shapes the service issues ──────────────
class _AggRow(SimpleNamespace):
    pass


class _FakeResult:
    def __init__(self, rows): self._rows = rows
    def all(self): return list(self._rows)
    def scalars(self):
        outer = self
        class _S:
            def all(s): return list(outer._rows)
        return _S()


class _FakeDB:
    """Returns the top-products aggregate rows for the grouped query, and ProductMentionLog rows
    for the drill-down query — distinguished by whether the SQL groups by product_name."""
    def __init__(self, agg_rows, mention_rows):
        self._agg = agg_rows
        self._mentions = mention_rows
    async def execute(self, q):
        sql = str(q).lower()
        if "group by" in sql:
            return _FakeResult(self._agg)
        return _FakeResult(self._mentions)


LAST = datetime(2026, 5, 4, 9, 30)

AGG = [
    _AggRow(product_name="گوشی سامسونگ A54", product_id=None, mention_count=42, group_count=7, sender_count=15, last_mention=LAST),
    _AggRow(product_name="iPhone 15", product_id=None, mention_count=30, group_count=5, sender_count=12, last_mention=datetime(2026, 5, 3, 8, 0)),
]


def _mention(**kw):
    base = dict(product_name="گوشی سامسونگ A54", product_id=None, sender_phone="989121112233",
                sender_name="فروشگاه پارس", group_name="بازار موبایل تهران",
                message_text="سامسونگ A54 موجود شد، تماس: 09124445566", mentioned_at=LAST)
    base.update(kw)
    return SimpleNamespace(**base)


MENTIONS = [
    _mention(),
    _mention(sender_phone="989350001122", sender_name="موبایل امید",
             message_text="A54 دارم", mentioned_at=datetime(2026, 5, 4, 8, 0)),
]


# ── the public top-products payload matches the UI endpoint's product data ────────────────────
@pytest.mark.asyncio
async def test_public_top_products_matches_ui_endpoint():
    db = _FakeDB(AGG, MENTIONS)
    ui_out = await ui.top_repeated_products(limit=30, days=30, db=db)
    pub_out = await pub.public_top_products(range=30, limit=30, db=db)

    assert pub_out["range_days"] == 30 and pub_out["limit"] == 30
    assert pub_out["count"] == ui_out["total_products"] == len(AGG)
    assert "generated_at" in pub_out

    for u, p in zip(ui_out["products"], pub_out["products"]):
        assert p["rank"] == u["rank"]
        assert p["product_name"] == u["product_name"]
        assert p["mention_count"] == u["mention_count"]
        assert p["group_count"] == u["group_count"]
        assert p["sender_count"] == u["sender_count"]
        # UI shows Shamsi; public adds the machine-readable ISO (both from the same raw datetime)
        assert p["last_mentioned_shamsi"] == u["last_mention_shamsi"]

    top = pub_out["products"][0]
    assert top["product_name"] == "گوشی سامسونگ A54" and top["mention_count"] == 42
    assert top["last_mentioned_at"] == LAST.isoformat()


# ── the public mentioners payload matches the UI «فروشندگان اخیر» drill-down ───────────────────
@pytest.mark.asyncio
async def test_public_mentioners_match_ui_sellers():
    db = _FakeDB(AGG, MENTIONS)
    name = "گوشی سامسونگ A54"
    ui_out = await ui.product_sellers(product_name=name, days=30, limit=100, db=db)
    pub_out = await pub.public_product_mentioners(product_name=name, range=30, limit=100, db=db)

    assert pub_out["product_name"] == name
    assert pub_out["count"] == ui_out["total_sellers"] == len(MENTIONS)

    for s, m in zip(ui_out["sellers"], pub_out["mentioners"]):
        assert m["sender_display_name"] == s["sender_name"]
        assert m["sender_phone"] == s["sender_phone"]
        assert m["group_name"] == s["group_name"]
        assert m["all_contacts"] == s["all_contacts"]
        assert m["timestamp_shamsi"] == s["time_shamsi"]

    # first row: sender's own number (primary) + the extra number in the message (secondary)
    first = pub_out["mentioners"][0]
    assert first["sender_phone"] == "09121112233"            # sender's own, normalized
    assert first["sender_phone_secondary"] == "09124445566"  # extracted from message text
    assert first["timestamp"] == LAST.isoformat()
    # second row lists no extra number → secondary is None
    assert pub_out["mentioners"][1]["sender_phone_secondary"] is None


@pytest.mark.asyncio
async def test_range_is_days_passthrough():
    db = _FakeDB(AGG, MENTIONS)
    out = await pub.public_top_products(range=7, limit=50, db=db)
    assert out["range_days"] == 7 and out["limit"] == 50


# ── the public top-products endpoint now honors a limit up to 1000 (matches the UI ceiling) ──
@pytest.mark.asyncio
async def test_public_top_products_limit_up_to_1000():
    rows = [
        _AggRow(product_name=f"محصول {i}", product_id=None, mention_count=1000 - i,
                group_count=1, sender_count=1, last_mention=LAST)
        for i in range(1000)
    ]
    out = await pub.public_top_products(range=36500, limit=1000, db=_FakeDB(rows, []))
    # Previously the public endpoint clamped this to 500; it now honors the full 1000.
    assert out["limit"] == 1000
    assert out["count"] == 1000
    assert out["products"][0]["rank"] == 1 and out["products"][-1]["rank"] == 1000


@pytest.mark.asyncio
async def test_public_top_products_clamps_above_1000():
    # Above the shared ceiling, it still clamps to 1000 (no unbounded query).
    out = await pub.public_top_products(range=30, limit=5000, db=_FakeDB(AGG, []))
    assert out["limit"] == 1000


# ── scoped, env-configurable CORS allowlist ───────────────────────────────────────────────────
def test_default_allowlist_includes_the_lan_origin():
    from app.config import settings
    allowed = pub.parse_allowed_origins(settings.reports_allowed_origins)
    assert "http://192.168.170.8:3100" in allowed


def test_cors_echoes_allowed_origin():
    allowed = ["http://192.168.170.8:3100", "http://192.168.170.10:3100"]
    h = pub.cors_headers_for("http://192.168.170.8:3100", allowed)
    assert h["Access-Control-Allow-Origin"] == "http://192.168.170.8:3100"
    assert h["Access-Control-Allow-Methods"] == "GET, OPTIONS"
    assert h["Vary"] == "Origin"


def test_cors_blocks_disallowed_origin():
    allowed = ["http://192.168.170.8:3100"]
    assert pub.cors_headers_for("http://evil.example.com", allowed) == {}


def test_cors_wildcard_allows_any_origin_but_echoes_it():
    h = pub.cors_headers_for("http://anything:9999", ["*"])
    assert h["Access-Control-Allow-Origin"] == "http://anything:9999"   # echo, not "*", with an Origin


def test_cors_wildcard_no_origin_returns_star():
    assert pub.cors_headers_for(None, ["*"])["Access-Control-Allow-Origin"] == "*"


def test_parse_allowed_origins_trims_and_drops_blanks():
    assert pub.parse_allowed_origins("a, b ,, c ") == ["a", "b", "c"]
    assert pub.parse_allowed_origins("") == []
    assert pub.parse_allowed_origins(None) == []
