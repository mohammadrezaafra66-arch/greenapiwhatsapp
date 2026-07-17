"""V26 PART 5 — group-monitoring UI endpoints + admin alerts.

Drives the endpoint functions directly with fake sessions:
  • available-groups merge annotates WhatsApp groups with their monitored state;
  • monitored upsert/patch persist toggles and reject an invalid conversation_mode;
  • keyword + predefined-reply CRUD works and validates kind;
  • messages/alerts endpoints return the captured data;
  • marking an alert read persists.
"""
import uuid
import pytest
from types import SimpleNamespace

from app.api.v1 import group_monitor as api
from app.models.group_monitor import (
    MonitoredGroup, GroupMessage, GroupKeyword, GroupPredefinedReply, GroupForbiddenAlert,
    CONVERSATION_MODE_OFF, CONVERSATION_MODE_AI,
)


# ── pure merge ───────────────────────────────────────────────────────────────
def test_merge_groups_with_monitored():
    m = MonitoredGroup(listener_instance_id="7105", group_id="g1@g.us", group_name="مانیتور",
                       is_monitored=True, auto_reply_enabled=True,
                       conversation_mode=CONVERSATION_MODE_AI)
    m.id = uuid.uuid4()
    wa = [{"id": "g1@g.us", "name": "گروه یک"}, {"id": "g2@g.us", "name": "گروه دو"}]
    out = api.merge_groups_with_monitored(wa, [m])
    g1 = next(g for g in out if g["group_id"] == "g1@g.us")
    g2 = next(g for g in out if g["group_id"] == "g2@g.us")
    assert g1["is_monitored"] and g1["auto_reply_enabled"]
    assert g1["conversation_mode"] == CONVERSATION_MODE_AI and g1["monitored_id"] == str(m.id)
    assert not g2["is_monitored"] and g2["conversation_mode"] == CONVERSATION_MODE_OFF


# ── fake session ─────────────────────────────────────────────────────────────
class _Scalars:
    def __init__(self, items): self._items = items
    def all(self): return list(self._items)


class _Result:
    def __init__(self, items): self._items = list(items)
    def scalars(self): return _Scalars(self._items)
    def scalar_one_or_none(self): return self._items[0] if self._items else None


class _FakeDB:
    """Returns configured rows for select() by target entity; records add/delete/commit."""
    def __init__(self, rows_by_entity=None, get_map=None):
        self.rows_by_entity = rows_by_entity or {}
        self.get_map = get_map or {}
        self.added = []
        self.deleted = []
        self.committed = 0

    async def execute(self, q):
        entity = None
        try:
            entity = q.column_descriptions[0]["entity"]
        except Exception:
            pass
        return _Result(self.rows_by_entity.get(entity, []))

    async def get(self, model, pk): return self.get_map.get(str(pk))
    def add(self, obj):
        self.added.append(obj)
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
    async def delete(self, obj): self.deleted.append(obj)
    async def commit(self): self.committed += 1
    async def refresh(self, obj): pass


# ── monitored groups ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_upsert_monitored_creates_new():
    db = _FakeDB(rows_by_entity={MonitoredGroup: []})
    body = api.MonitoredUpsert(listener_instance_id="7105", group_id="g@g.us",
                               group_name="G", is_monitored=True,
                               auto_reply_enabled=True, conversation_mode=CONVERSATION_MODE_AI)
    out = await api.upsert_monitored(body, db=db)
    assert out["conversation_mode"] == CONVERSATION_MODE_AI and out["auto_reply_enabled"]
    assert len(db.added) == 1 and db.committed == 1


@pytest.mark.asyncio
async def test_upsert_monitored_rejects_bad_mode():
    db = _FakeDB()
    body = api.MonitoredUpsert(listener_instance_id="7105", group_id="g@g.us",
                               conversation_mode="banana")
    with pytest.raises(Exception):
        await api.upsert_monitored(body, db=db)


@pytest.mark.asyncio
async def test_patch_monitored_toggles_persist():
    m = MonitoredGroup(listener_instance_id="7105", group_id="g@g.us",
                       is_monitored=True, auto_reply_enabled=False,
                       conversation_mode=CONVERSATION_MODE_OFF)
    m.id = uuid.uuid4()
    db = _FakeDB(get_map={str(m.id): m})
    out = await api.patch_monitored(str(m.id),
                                    api.MonitoredPatch(auto_reply_enabled=True,
                                                       conversation_mode=CONVERSATION_MODE_AI),
                                    db=db)
    assert out["auto_reply_enabled"] and out["conversation_mode"] == CONVERSATION_MODE_AI
    assert m.auto_reply_enabled and db.committed == 1


@pytest.mark.asyncio
async def test_patch_monitored_bad_mode_rejected():
    m = MonitoredGroup(listener_instance_id="7105", group_id="g@g.us")
    m.id = uuid.uuid4()
    db = _FakeDB(get_map={str(m.id): m})
    with pytest.raises(Exception):
        await api.patch_monitored(str(m.id), api.MonitoredPatch(conversation_mode="x"), db=db)


# ── keyword CRUD ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_keyword_create_and_validate():
    db = _FakeDB()
    out = await api.create_keyword(api.KeywordBody(word=" قیمت ", kind="trigger"), db=db)
    assert out["word"] == "قیمت" and out["kind"] == "trigger"
    assert len(db.added) == 1
    with pytest.raises(Exception):
        await api.create_keyword(api.KeywordBody(word="x", kind="bogus"), db=db)
    with pytest.raises(Exception):
        await api.create_keyword(api.KeywordBody(word="   ", kind="trigger"), db=db)


@pytest.mark.asyncio
async def test_keyword_list_and_delete():
    k = GroupKeyword(word="موجودی", kind="trigger", active=True); k.id = uuid.uuid4()
    db = _FakeDB(rows_by_entity={GroupKeyword: [k]}, get_map={str(k.id): k})
    lst = await api.list_keywords(db=db)
    assert lst[0]["word"] == "موجودی"
    out = await api.delete_keyword(str(k.id), db=db)
    assert out["deleted"] and db.deleted == [k]


# ── predefined replies ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_reply_create_and_list():
    db = _FakeDB(rows_by_entity={GroupPredefinedReply: []})
    kid = str(uuid.uuid4())
    out = await api.create_reply(api.ReplyBody(reply_text="سلام", keyword_id=kid), db=db)
    assert "id" in out and len(db.added) == 1
    with pytest.raises(Exception):
        await api.create_reply(api.ReplyBody(reply_text="  "), db=db)


# ── messages + alerts ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_list_messages_shapes_voice_and_keywords():
    m = GroupMessage(listener_instance_id="7105", group_id="g@g.us", group_name="G",
                     sender="s@c.us", sender_name="علی", id_message="M1",
                     type_message="audioMessage", is_voice=True,
                     transcription="قیمت یخچال", transcription_status="done",
                     matched_keywords="قیمت", flagged_forbidden=False, replied=True)
    m.id = uuid.uuid4()
    db = _FakeDB(rows_by_entity={GroupMessage: [m]})
    out = await api.list_messages(group_id="g@g.us", db=db)
    assert out[0]["is_voice"] and out[0]["transcription"] == "قیمت یخچال"
    assert out[0]["matched_keywords"] == "قیمت" and out[0]["replied"]


@pytest.mark.asyncio
async def test_list_alerts_and_mark_read():
    a = GroupForbiddenAlert(listener_instance_id="7105", group_id="g@g.us", group_name="G",
                            sender="s@c.us", sender_name="علی", word="کلاهبرداری",
                            message_text="متن", is_read=False)
    a.id = uuid.uuid4()
    db = _FakeDB(rows_by_entity={GroupForbiddenAlert: [a]}, get_map={str(a.id): a})
    lst = await api.list_alerts(db=db)
    assert lst[0]["word"] == "کلاهبرداری" and lst[0]["is_read"] is False
    out = await api.mark_alert_read(str(a.id), db=db)
    assert out["is_read"] and a.is_read is True
