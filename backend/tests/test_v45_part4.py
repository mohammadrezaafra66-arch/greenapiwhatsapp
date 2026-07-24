"""V45 PART 4 — end-to-end: exclusion + harvesting behave correctly together across the real wiring.

MESSAGE path (drives the actual webhook handle_incoming): a group message from an EXCLUDED own
number triggers zero detection calls, zero product-mention rows, and is NOT harvested; a message from
a genuine OUTSIDE number is detected/counted AND harvested — and a repeat sighting bumps the same
harvested row without ever creating a duplicate.

STORY path: an own-number story is neither analyzed (no vision call, no analysis row) nor harvested,
while an outside story is analyzed AND harvested.
"""
import uuid
from types import SimpleNamespace

import pytest

from app.services.own_number_exclusion import normalize_own_number
from app.services.active_contact_harvest import harvest_status_senders

OWN_PHONE = "989121110001"
OUT_PHONE = "989129990002"
OWN_CORE = normalize_own_number(OWN_PHONE)
OUT_CORE = normalize_own_number(OUT_PHONE)
INSTANCE = "v45p4_inst"


class _Res:
    def __init__(self, rows): self._rows = list(rows)
    def scalars(self): return self
    def all(self): return list(self._rows)
    def scalar_one_or_none(self): return self._rows[0] if self._rows else None


class FakeE2ESession:
    """One shared-state fake session for the whole webhook flow: answers the exclusion query, the
    our-cores query, account/entity lookups, and the ActiveWhatsappContact dedup lookup; collects
    every added row. State (cores/contacts/sink) is shared across sessions so repeated webhook calls
    see the previously-harvested contact (proving cross-call dedup)."""
    def __init__(self, state): self.state = state
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def execute(self, q):
        try:
            cds = q.column_descriptions
        except Exception:
            return _Res([])
        name = cds[0].get("name") if cds else None
        if name == "phone_core":
            return _Res(list(self.state["cores"]))
        if name == "phone":
            return _Res([])
        if name == "ActiveWhatsappContact":
            target = q.compile().params.get("phone_core_1")
            c = self.state["contacts"].get(target)
            return _Res([c] if c else [])
        return _Res([])
    def add(self, o):
        from app.models.active_contact import ActiveWhatsappContact
        if getattr(o, "id", None) is None:
            o.id = uuid.uuid4()
        self.state["sink"].append(o)
        if isinstance(o, ActiveWhatsappContact):
            self.state["contacts"][o.phone_core] = o
    async def get(self, *a): return None
    async def commit(self): pass
    async def rollback(self): pass
    async def refresh(self, o): pass


def _install(monkeypatch, cores):
    state = {"cores": set(cores), "contacts": {}, "sink": []}
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
    monkeypatch.setattr("app.api.v1.webhook.AsyncSessionLocal", lambda: FakeE2ESession(state))
    return state, calls


def _group_payload(phone, mid):
    return {
        "typeWebhook": "incomingMessageReceived", "idMessage": mid, "timestamp": 1700000000,
        "senderData": {"chatId": "120363999@g.us", "sender": f"{phone}@c.us",
                       "senderName": "Seller", "chatName": "بازار"},
        "messageData": {"typeMessage": "textMessage", "textMessageData": {"textMessage": "لپ‌تاپ ایسوس"}},
        "instanceData": {"typeInstance": "whatsapp"},
    }


def _counts(sink):
    from app.models.reporting import ProductMentionLog
    from app.models.active_contact import ActiveWhatsappContact
    mentions = [o for o in sink if isinstance(o, ProductMentionLog)]
    contacts = [o for o in sink if isinstance(o, ActiveWhatsappContact)]
    return mentions, contacts


@pytest.mark.asyncio
async def test_e2e_excluded_own_number_zero_everything(monkeypatch):
    from app.api.v1.webhook import handle_incoming
    state, calls = _install(monkeypatch, {OWN_CORE})
    await handle_incoming(INSTANCE, _group_payload(OWN_PHONE, "own1"))
    mentions, contacts = _counts(state["sink"])
    assert calls == []            # zero detection / AI calls
    assert mentions == []         # zero product-mention rows
    assert contacts == []         # not harvested


@pytest.mark.asyncio
async def test_e2e_outside_number_detected_and_harvested_deduped(monkeypatch):
    from app.api.v1.webhook import handle_incoming
    state, calls = _install(monkeypatch, {OWN_CORE})     # OUT is not excluded
    # first sighting
    await handle_incoming(INSTANCE, _group_payload(OUT_PHONE, "out1"))
    mentions, contacts = _counts(state["sink"])
    assert calls == ["لپ‌تاپ ایسوس"]            # detection ran
    assert len(mentions) == 1 and mentions[0].sender_phone == OUT_PHONE and mentions[0].source == "group"
    assert len(contacts) == 1 and contacts[0].phone_core == OUT_CORE
    assert contacts[0].first_seen_source == "group" and contacts[0].sighting_count == 1
    # second sighting of the SAME outside number → still ONE harvested row, sighting bumped
    await handle_incoming(INSTANCE, _group_payload(OUT_PHONE, "out2"))
    mentions, contacts = _counts(state["sink"])
    assert len(contacts) == 1                    # never duplicated
    assert contacts[0].sighting_count == 2
    assert len(mentions) == 2                    # each message is still counted as a mention


# ── STORY path: own number excluded from BOTH analysis and harvest ────────────────────────────
def _story(phone, path):
    return SimpleNamespace(id=uuid.uuid4(), sender_phone=phone, sender_name="S", instance_id=INSTANCE,
                           status_type="image", local_media_path=path, media_downloaded=True,
                           text_content=None, caption=None)


class _StoryDB:
    def __init__(self): self.added = []
    async def execute(self, q): return _Res([])
    def add(self, o): self.added.append(o)
    async def get(self, *a): return None
    async def commit(self): pass


@pytest.mark.asyncio
async def test_e2e_story_own_number_not_analyzed_not_harvested(monkeypatch):
    from app.api.v1 import statuses as st

    async def _cores(_db): return {OWN_CORE}
    async def _our(_db): return set()
    async def _products(_n): return []
    monkeypatch.setattr("app.services.own_number_exclusion.get_excluded_cores", _cores)
    monkeypatch.setattr("app.services.catalog_spot_alert.get_our_phone_cores", _our)
    monkeypatch.setattr("app.services.price_service.get_products", _products)

    vision = []
    async def vision_spy(p): vision.append(p); return {"text": "gadget"}

    db = _StoryDB()
    results = await st._analyze_story_rows(
        db, [_story(OWN_PHONE, "/own.jpg"), _story(OUT_PHONE, "/out.jpg")], vision_fn=vision_spy)
    assert vision == ["/out.jpg"]        # own story never reached vision
    assert len(results) == 1

    # harvest side: own excluded, outside harvested (source='status')
    hdb = _StoryDB()
    async def _hcores(_db): return {OWN_CORE}
    monkeypatch.setattr("app.services.own_number_exclusion.get_excluded_cores", _hcores)
    statuses = [
        {"idMessage": "s1", "chatId": f"{OWN_PHONE}@c.us", "senderName": "ours",
         "typeMessage": "textStatusMessage", "textStatus": "x", "timestamp": 1758537600},
        {"idMessage": "s2", "chatId": f"{OUT_PHONE}@c.us", "senderName": "lead",
         "typeMessage": "textStatusMessage", "textStatus": "y", "timestamp": 1758537600},
    ]
    n = await harvest_status_senders(hdb, statuses)
    from app.models.active_contact import ActiveWhatsappContact
    harvested = [o for o in hdb.added if isinstance(o, ActiveWhatsappContact)]
    assert n == 1 and len(harvested) == 1
    assert harvested[0].phone_core == OUT_CORE and harvested[0].first_seen_source == "status"
