"""V40 PART 7 — catalog-product-spotted alert (price-free, deduped).

Proves: a CATALOG (in-assistant) product advertised by an OUTSIDE contact raises exactly one alert;
a non-catalog product raises none; one of our OWN accounts advertising it raises none; re-observing
the same (contact, product) the same day does not raise a duplicate.
"""
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services.catalog_spot_alert import maybe_raise_spot_alert
from app.models.catalog_alert import CatalogSpotAlert


class _Result:
    def __init__(self, row): self._row = row
    def first(self): return self._row


class _DB:
    """Dedups on (contact_phone, product_name, alert_date) like the real unique constraint."""
    def __init__(self):
        self.added = []
    async def execute(self, q):
        params = q.compile().params
        core = params.get("contact_phone_1")
        name = params.get("product_name_1")
        day = params.get("alert_date_1")
        for a in self.added:
            if a.contact_phone == core and a.product_name == name and a.alert_date == day:
                return _Result((a.id,))
        return _Result(None)
    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.added.append(obj)


OUR = {"9120000000"}
NOW = datetime(2026, 7, 22, 9, 0)


async def _raise(db, *, phone="989121112233", pid="cat-1", name="کولر گازی گری 18000", now=NOW):
    return await maybe_raise_spot_alert(
        db, contact_phone=phone, contact_name="فروشگاه پارس", product_name=name,
        product_id=pid, source="status", instance_id="i", message_text="x",
        our_cores=OUR, now=now)


@pytest.mark.asyncio
async def test_catalog_product_outside_contact_raises_one_alert():
    db = _DB()
    raised = await _raise(db)
    assert raised is True
    assert len(db.added) == 1
    a = db.added[0]
    assert isinstance(a, CatalogSpotAlert)
    assert a.contact_phone == "9121112233"           # stored as national core
    assert a.product_id == "cat-1"


@pytest.mark.asyncio
async def test_non_catalog_product_raises_nothing():
    db = _DB()
    raised = await _raise(db, pid=None)               # no product_id → not in assistant
    assert raised is False and db.added == []


@pytest.mark.asyncio
async def test_our_own_account_raises_nothing():
    db = _DB()
    raised = await _raise(db, phone="09120000000")    # matches OUR cores
    assert raised is False and db.added == []


@pytest.mark.asyncio
async def test_reobserving_same_contact_product_day_is_deduped():
    db = _DB()
    first = await _raise(db)
    second = await _raise(db)                          # same contact+product+day
    assert first is True and second is False
    assert len(db.added) == 1


@pytest.mark.asyncio
async def test_same_contact_different_product_raises_again():
    db = _DB()
    await _raise(db, name="کولر گازی گری 18000")
    again = await _raise(db, name="یخچال سامسونگ", pid="cat-2")
    assert again is True
    assert len(db.added) == 2


@pytest.mark.asyncio
async def test_next_day_same_advert_raises_again():
    db = _DB()
    await _raise(db, now=datetime(2026, 7, 22, 9, 0))
    nextday = await _raise(db, now=datetime(2026, 7, 23, 9, 0))
    assert nextday is True
    assert len(db.added) == 2
