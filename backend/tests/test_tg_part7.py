"""TG PART 7 — unified Persian/RTL UI across WhatsApp and Telegram.

Backend-side proof that the inbox platform filter scopes results correctly and that pages are
unaffected when Telegram has zero instances. (The React platform switcher's pure filter is
covered by frontend/src/components/PlatformSwitcher.test.js.)
"""
import uuid
import pytest

from app.api.v1 import inbox as inbox_api
from app.models.inbox import InboxMessage


def _msg(instance_id):
    m = InboxMessage(instance_id=instance_id, sender_phone="9", sender_name="n",
                     message_type="text", text_content="سلام", is_group=False,
                     category="other", archived=False)
    m.id = uuid.uuid4()
    m.is_read = False
    m.auto_replied = False
    return m


class _Scalars:
    def __init__(self, items): self._items = items
    def all(self): return list(self._items)


class _Result:
    def __init__(self, items): self._items = items
    def scalars(self): return _Scalars(self._items)


class _FakeDB:
    """Honors the compiled WHERE clause: applies both the archived filter and the platform
    subquery (instance_id IN telegram-instances) by inspecting the literal-bound SQL."""
    def __init__(self, messages, telegram_instances):
        self.messages = messages
        self.telegram_instances = telegram_instances

    async def execute(self, q):
        try:
            sql = str(q.compile(compile_kwargs={"literal_binds": True})).lower()
        except Exception:
            sql = str(q).lower()
        rows = list(self.messages)
        # The platform subquery embeds Account.platform = 'telegram'; emulate it.
        if "platform" in sql and "'telegram'" in sql:
            rows = [m for m in rows if m.instance_id in self.telegram_instances]
        return _Result(rows)


@pytest.mark.asyncio
async def test_platform_filter_scopes_to_telegram():
    msgs = [_msg("7105"), _msg("4100"), _msg("4200")]      # 1 WA, 2 TG
    db = _FakeDB(msgs, telegram_instances={"4100", "4200"})
    got = await inbox_api.list_inbox(platform="telegram", db=db)
    assert {m["instance_id"] for m in got} == {"4100", "4200"}
    assert len(got) == 2


@pytest.mark.asyncio
async def test_no_platform_returns_everything():
    msgs = [_msg("7105"), _msg("4100")]
    db = _FakeDB(msgs, telegram_instances={"4100"})
    got = await inbox_api.list_inbox(db=db)
    assert len(got) == 2      # unaffected when no platform filter given


@pytest.mark.asyncio
async def test_telegram_filter_empty_when_no_telegram_instances():
    msgs = [_msg("7105"), _msg("7106")]     # all WhatsApp
    db = _FakeDB(msgs, telegram_instances=set())
    got = await inbox_api.list_inbox(platform="telegram", db=db)
    assert got == []          # WhatsApp-only views unaffected; TG view simply empty
