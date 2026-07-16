"""V25 PART 2 — inbox account filter.

The inbox endpoint filters incoming messages SERVER-SIDE by instance_id: selecting an
account returns only that account's messages; the "all" option (instance_id=None) returns
everything. These tests drive `list_inbox` with a fake session that honours the compiled
WHERE clause, so the filtering is genuinely exercised (not just asserted on the query text).
"""
import uuid
import pytest

from app.api.v1 import inbox as inbox_api
from app.models.inbox import InboxMessage


def _msg(instance_id, phone):
    m = InboxMessage(instance_id=instance_id, sender_phone=phone, sender_name=phone,
                     message_type="text", text_content="سلام", is_group=False,
                     category="other", archived=False)
    m.id = uuid.uuid4()
    m.is_read = False
    m.auto_replied = False
    return m


class FakeScalars:
    def __init__(self, items): self._items = list(items)
    def all(self): return list(self._items)


class FakeResult:
    def __init__(self, items): self._items = list(items)
    def scalars(self): return FakeScalars(self._items)


class FakeInboxDB:
    """Applies the endpoint's instance_id WHERE clause against an in-memory message list, so
    'only that account's messages' is a real filter, not a stub."""
    def __init__(self, messages):
        self.messages = list(messages)

    async def execute(self, q):
        try:
            sql = str(q.compile(compile_kwargs={"literal_binds": True})).lower()
        except Exception:
            sql = str(q).lower()
        rows = list(self.messages)
        # all seeded messages are non-archived; the endpoint always filters archived=false
        if "instance_id =" in sql:
            rows = [m for m in rows if m.instance_id.lower() in sql]
        return FakeResult(rows)


@pytest.mark.asyncio
async def test_filter_by_account_returns_only_that_account():
    msgs = [_msg("inst1101", "9891"), _msg("inst1101", "9892"), _msg("inst2202", "9893")]
    db = FakeInboxDB(msgs)
    got = await inbox_api.list_inbox(instance_id="inst1101", db=db)
    assert {m["instance_id"] for m in got} == {"inst1101"}
    assert len(got) == 2


@pytest.mark.asyncio
async def test_all_accounts_returns_everything():
    msgs = [_msg("inst1101", "9891"), _msg("inst2202", "9893"), _msg("inst3303", "9894")]
    db = FakeInboxDB(msgs)
    got = await inbox_api.list_inbox(instance_id=None, db=db)
    assert {m["instance_id"] for m in got} == {"inst1101", "inst2202", "inst3303"}
    assert len(got) == 3


@pytest.mark.asyncio
async def test_filter_nonmatching_account_returns_empty():
    msgs = [_msg("inst1101", "9891"), _msg("inst2202", "9893")]
    db = FakeInboxDB(msgs)
    got = await inbox_api.list_inbox(instance_id="inst9999", db=db)
    assert got == []
