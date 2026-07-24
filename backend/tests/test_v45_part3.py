"""V45 PART 3 — active WhatsApp contacts harvesting list.

Hermetic. Proves:
  • a number seen for the first time creates exactly one row (source recorded);
  • the SAME number seen again (any format) bumps last_seen + sighting_count with NO duplicate row;
  • an excluded (own) number is never harvested;
  • the display name is backfilled on a later sighting when it was unknown;
  • message-source classification (group/channel/broadcast, private → not harvested);
  • story-batch harvesting excludes own numbers;
  • the list/export API returns items and sequential row numbers.
"""
import uuid
from datetime import datetime, timedelta

import pytest

from app.models.active_contact import ActiveWhatsappContact
from app.services import active_contact_harvest as h
from app.services.active_contact_harvest import (
    upsert_active_contact, harvest_status_senders, message_source_for_chat_id)
from app.api.v1.active_contacts import list_active_contacts, export_active_contacts


class _Res:
    def __init__(self, rows): self._rows = list(rows)
    def scalars(self): return self
    def all(self): return list(self._rows)
    def scalar_one_or_none(self): return self._rows[0] if self._rows else None


class FakeHarvestDB:
    def __init__(self, cores=None):
        self.contacts = {}                 # phone_core -> ActiveWhatsappContact
        self.cores = set(cores or set())
        self.added = []

    async def execute(self, q):
        cds = q.column_descriptions
        name = cds[0].get("name")
        if name == "phone_core":                       # get_excluded_cores
            return _Res(list(self.cores))
        target = q.compile().params.get("phone_core_1")  # select(ActiveWhatsappContact).where(...)
        if target is not None:
            c = self.contacts.get(target)
            return _Res([c] if c else [])
        return _Res(list(self.contacts.values()))       # list/export (no where)

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.added.append(obj)
        self.contacts[obj.phone_core] = obj

    async def commit(self): pass


# ── first sighting → exactly one row ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_first_sighting_creates_one_row():
    db = FakeHarvestDB()
    row = await upsert_active_contact(db, "989121234567", name="فروشگاه", source="group",
                                      excluded_cores=set())
    assert row is not None
    assert len(db.added) == 1
    assert row.phone_core == "9121234567"
    assert row.first_seen_source == "group"
    assert row.sighting_count == 1
    assert row.display_name == "فروشگاه"


# ── same number again (any format) → last_seen bumped, NO duplicate ────────────────────────────
@pytest.mark.asyncio
async def test_same_number_again_no_duplicate():
    db = FakeHarvestDB()
    t0 = datetime(2026, 7, 24, 8, 0, 0)
    t1 = t0 + timedelta(hours=3)
    await upsert_active_contact(db, "989121234567", name="A", source="status",
                                excluded_cores=set(), now=t0)
    row = await upsert_active_contact(db, "09121234567", name="A", source="group",
                                      excluded_cores=set(), now=t1)   # SAME number, other format
    assert len(db.added) == 1                       # never a second row
    assert row.sighting_count == 2
    assert row.last_seen_at == t1
    assert row.first_seen_at == t0                  # first-seen preserved
    assert row.first_seen_source == "status"        # first source preserved


# ── an excluded (own) number is never harvested ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_own_number_never_harvested():
    db = FakeHarvestDB()
    row = await upsert_active_contact(db, "989121234567", name="ours", source="group",
                                      excluded_cores={"9121234567"})
    assert row is None
    assert db.added == []


@pytest.mark.asyncio
async def test_blank_number_skipped():
    db = FakeHarvestDB()
    assert await upsert_active_contact(db, "", name=None, source="group", excluded_cores=set()) is None
    assert await upsert_active_contact(db, None, name=None, source="group", excluded_cores=set()) is None
    assert db.added == []


# ── name backfilled on a later sighting when unknown before ───────────────────────────────────
@pytest.mark.asyncio
async def test_name_backfilled_when_previously_unknown():
    db = FakeHarvestDB()
    await upsert_active_contact(db, "989121234567", name=None, source="group", excluded_cores=set())
    row = await upsert_active_contact(db, "989121234567", name="Shop", source="group", excluded_cores=set())
    assert row.display_name == "Shop"
    assert len(db.added) == 1


# ── source classification reuses the chat-id convention; private is never harvested ───────────
def test_message_source_classification():
    assert message_source_for_chat_id("120363000000000000@g.us") == "group"
    assert message_source_for_chat_id("123@newsletter") == "channel"
    assert message_source_for_chat_id("123@broadcast") == "broadcast"
    assert message_source_for_chat_id("989121234567@c.us") is None      # private DM → not harvested
    assert message_source_for_chat_id("") is None
    assert message_source_for_chat_id(None) is None


# ── story-batch harvest excludes own numbers, tags source='status' ────────────────────────────
@pytest.mark.asyncio
async def test_harvest_status_senders_excludes_own():
    db = FakeHarvestDB(cores={"9121234567"})     # first number is ours
    statuses = [
        {"idMessage": "1", "chatId": "989121234567@c.us", "senderName": "ours",
         "typeMessage": "textStatusMessage", "textStatus": "x", "timestamp": 1758537600},
        {"idMessage": "2", "chatId": "989129999999@c.us", "senderName": "lead",
         "typeMessage": "textStatusMessage", "textStatus": "y", "timestamp": 1758537600},
    ]
    n = await harvest_status_senders(db, statuses)
    assert n == 1
    assert len(db.added) == 1
    only = db.added[0]
    assert only.phone_core == "9129999999" and only.first_seen_source == "status"


# ── list + export API: items returned and sequential row numbers in the CSV ───────────────────
@pytest.mark.asyncio
async def test_list_and_export_api():
    db = FakeHarvestDB()
    now = datetime(2026, 7, 24, 8, 0, 0)
    await upsert_active_contact(db, "989121111111", name="A", source="group", excluded_cores=set(), now=now)
    await upsert_active_contact(db, "989122222222", name="B", source="status", excluded_cores=set(), now=now)

    listed = await list_active_contacts(db=db)
    assert listed["count"] == 2
    labels = {it["source_label"] for it in listed["items"]}
    assert "گروه" in labels and "استوری" in labels

    resp = await export_active_contacts(db=db)
    body = resp.body.decode("utf-8")
    assert "row,phone,name,source" in body
    assert "\n1," in body and "\n2," in body        # sequential row numbers present
