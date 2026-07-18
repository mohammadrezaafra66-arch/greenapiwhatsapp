"""V26 PART 1 — group-monitoring schema + listener designation.

Proves:
  • the four V26 tables (+ admin-alert table) are registered on Base.metadata with the
    spec'd columns (so create_all / the idempotent DDL builds them);
  • model instances construct with the expected defaults (CRUD-shape);
  • the listener-role mutual-exclusion guard blocks every conflicting role in BOTH
    directions, with Persian errors, and allows a clean dedicated number.
"""
import uuid
import pytest
from types import SimpleNamespace

from app.database import Base
from app.models.group_monitor import (
    MonitoredGroup, GroupMessage, GroupKeyword, GroupPredefinedReply, GroupForbiddenAlert,
    CONVERSATION_MODE_OFF, KEYWORD_KIND_TRIGGER, KEYWORD_KIND_FORBIDDEN, TRANSCRIPTION_NONE,
    TRANSCRIPTION_PENDING,
)
from app.models.account import Account
from app.services import listener_service as ls


# ── schema presence ──────────────────────────────────────────────────────────
def test_all_v26_tables_registered():
    tables = Base.metadata.tables
    for name in ("monitored_group", "group_message", "group_keyword",
                 "group_predefined_reply", "group_forbidden_alert"):
        assert name in tables, f"{name} not registered on Base.metadata"


def test_group_message_has_all_spec_columns():
    cols = set(Base.metadata.tables["group_message"].columns.keys())
    expected = {
        "id", "listener_instance_id", "group_id", "group_name", "sender", "sender_name",
        "id_message", "type_message", "text", "is_voice", "audio_url", "audio_local_path",
        "transcription", "transcription_status", "matched_keywords", "flagged_forbidden",
        "replied", "timestamp", "created_at",
    }
    assert expected <= cols, f"missing: {expected - cols}"


def test_id_message_is_unique_for_dedupe():
    assert Base.metadata.tables["group_message"].columns["id_message"].unique is True


def test_monitored_group_defaults_off_and_no_autoreply():
    mg = MonitoredGroup(listener_instance_id="7105", group_id="123-456@g.us", group_name="G")
    # defaults applied at flush; assert the column server/py defaults are what we expect.
    assert MonitoredGroup.__table__.c.auto_reply_enabled.default.arg is False
    assert MonitoredGroup.__table__.c.conversation_mode.default.arg == CONVERSATION_MODE_OFF
    assert MonitoredGroup.__table__.c.is_monitored.default.arg is True


def test_account_has_is_listener_column():
    assert "is_listener" in Account.__table__.columns.keys()
    assert Account.__table__.c.is_listener.default.arg is False


# ── model construction (CRUD-shape) ──────────────────────────────────────────
def test_construct_all_four_models():
    kw = GroupKeyword(word="قیمت", kind=KEYWORD_KIND_TRIGGER)
    fb = GroupKeyword(word="کلاهبرداری", kind=KEYWORD_KIND_FORBIDDEN)
    reply = GroupPredefinedReply(keyword_id=uuid.uuid4(), reply_text="قیمت را خصوصی بفرستید")
    mg = MonitoredGroup(listener_instance_id="7105", group_id="g@g.us")
    gm = GroupMessage(listener_instance_id="7105", group_id="g@g.us",
                      id_message="ABC123", type_message="audioMessage", is_voice=True,
                      audio_url="http://x/a.ogg", transcription_status=TRANSCRIPTION_PENDING)
    assert kw.word == "قیمت" and fb.kind == KEYWORD_KIND_FORBIDDEN
    assert reply.reply_text.startswith("قیمت")
    assert mg.group_id.endswith("@g.us")
    assert gm.is_voice and gm.transcription_status == TRANSCRIPTION_PENDING


# ── pure mutual-exclusion guard ──────────────────────────────────────────────
def test_clean_number_can_be_listener():
    ok, err = ls.can_mark_as_listener(is_warm_peer=False, auto_warmup=False,
                                      is_actively_warming=False)
    assert ok and err is None


def test_warm_peer_cannot_be_listener():
    ok, err = ls.can_mark_as_listener(is_warm_peer=True, auto_warmup=False,
                                      is_actively_warming=False)
    assert not ok and "همتای گرم‌سازی" in err


def test_actively_warming_cannot_be_listener():
    ok, err = ls.can_mark_as_listener(is_warm_peer=False, auto_warmup=False,
                                      is_actively_warming=True)
    assert not ok and "گرم‌سازی" in err


def test_auto_warmup_cannot_be_listener():
    ok, err = ls.can_mark_as_listener(is_warm_peer=False, auto_warmup=True,
                                      is_actively_warming=False)
    assert not ok and err


def test_listener_cannot_be_warm_peer():
    ok, err = ls.can_mark_as_warm_peer(is_listener=True)
    assert not ok and "شنونده" in err
    ok2, err2 = ls.can_mark_as_warm_peer(is_listener=False)
    assert ok2 and err2 is None


def test_listener_cannot_enroll_in_warmup():
    ok, err = ls.can_enroll_in_warmup(is_listener=True)
    assert not ok and "شنونده" in err
    assert ls.can_enroll_in_warmup(is_listener=False)[0] is True


def test_listener_campaign_excluded():
    assert ls.listener_campaign_excluded(SimpleNamespace(is_listener=True)) is True
    assert ls.listener_campaign_excluded(SimpleNamespace(is_listener=False)) is False
    assert ls.listener_campaign_excluded(SimpleNamespace()) is False


# ── set_listener with a fake DB / enrollment map ─────────────────────────────
class _FakeResult:
    def __init__(self, rows): self._rows = rows
    def all(self): return list(self._rows)


class _FakeDB:
    """Only needs .execute() → rows for enrollment_states_by_instance()."""
    def __init__(self, enrollment_rows): self._rows = enrollment_rows
    async def execute(self, q): return _FakeResult(self._rows)


@pytest.mark.asyncio
async def test_set_listener_success_on_clean_account():
    acc = SimpleNamespace(instance_id="7105", is_warm_peer=False, auto_warmup=False,
                          is_listener=False)
    db = _FakeDB([])  # no enrollments
    ok, err = await ls.set_listener(db, acc, True)
    assert ok and err is None and acc.is_listener is True


@pytest.mark.asyncio
async def test_set_listener_blocked_when_actively_warming():
    acc = SimpleNamespace(instance_id="7105", is_warm_peer=False, auto_warmup=False,
                          is_listener=False)
    # active (is_enabled=True), non-graduated enrollment for this instance
    db = _FakeDB([("7105", "RECEIVING", True)])
    ok, err = await ls.set_listener(db, acc, True)
    assert not ok and err and acc.is_listener is False


@pytest.mark.asyncio
async def test_set_listener_blocked_when_warm_peer():
    acc = SimpleNamespace(instance_id="7105", is_warm_peer=True, auto_warmup=False,
                          is_listener=False)
    db = _FakeDB([])
    ok, err = await ls.set_listener(db, acc, True)
    assert not ok and "همتای گرم‌سازی" in err


@pytest.mark.asyncio
async def test_clearing_listener_is_always_allowed():
    acc = SimpleNamespace(instance_id="7105", is_warm_peer=False, auto_warmup=False,
                          is_listener=True)
    db = _FakeDB([("7105", "RECEIVING", True)])  # even mid-warm, clearing must work
    ok, err = await ls.set_listener(db, acc, False)
    assert ok and acc.is_listener is False
