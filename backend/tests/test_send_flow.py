"""
Integration tests for the critical send / webhook / rate-limit paths.

These exercise the REAL function logic while mocking the I/O boundaries
(Green API client, DB session, Redis) with AsyncMock. No live DB/Redis/HTTP.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.account import Account, AccountStatus
from app.models.contact import Contact
from app.models.campaign import Campaign, CampaignContact, CampaignStatus, CampaignType, MessageStatus


# ── Fake async DB primitives ───────────────────────────────
class FakeScalars:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return list(self._items)

    def first(self):
        return self._items[0] if self._items else None


class FakeResult:
    def __init__(self, rows=None, scalars=None):
        self._rows = rows or []
        self._scalars = scalars if scalars is not None else []

    def all(self):
        return list(self._rows)

    def scalars(self):
        return FakeScalars(self._scalars)

    def scalar_one_or_none(self):
        return self._scalars[0] if self._scalars else None


class FakeSession:
    """Minimal async-session double. execute() returns queued FakeResults in order;
    get() returns objects keyed by model name."""
    def __init__(self, results=None, gets=None):
        self._results = list(results or [])
        self._gets = dict(gets or {})
        self.added = []
        self.commits = 0
        self.refreshes = 0

    async def get(self, model, pk):
        return self._gets.get(model.__name__)

    async def execute(self, query):
        return self._results.pop(0) if self._results else FakeResult()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        self.refreshes += 1

    async def delete(self, obj):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def sessionmaker(session):
    """Mimic AsyncSessionLocal() -> async context manager."""
    return lambda: session


# ── Object builders (transient ORM instances) ──────────────
def make_account(**over):
    a = Account(name="Test", instance_id="7105325764", api_token="tok")
    a.id = uuid.uuid4()
    a.status = AccountStatus.active
    a.sent_today = 0
    a.received_today = 0
    a.received_yesterday = 0
    a.quick_replies_yesterday = 0
    a.days_active = 5
    a.daily_limit = 50
    for k, v in over.items():
        setattr(a, k, v)
    return a


def make_contact(**over):
    c = Contact(phone="989123456789")
    c.id = uuid.uuid4()
    c.first_name = "رضا"
    c.last_name = "الف"
    c.blacklisted = False
    c.has_whatsapp = None
    for k, v in over.items():
        setattr(c, k, v)
    return c


def make_campaign(**over):
    c = Campaign(name="کمپین تست")
    c.id = uuid.uuid4()
    c.status = CampaignStatus.running
    c.campaign_type = CampaignType.text
    c.use_gpt = False  # template path — no GPT/product fetch needed
    c.gpt_prompt = None
    c.message_template = "سلام {{first_name}} جان"
    c.include_products = False
    c.product_count = 3
    c.campaign_scope = "pv"
    c.group_ids = None
    c.pause_reason = None
    c.poll_options = None
    c.poll_question = None
    c.button1_text = c.button2_text = c.button3_text = None
    c.footer_text = None
    c.image_url = None
    c.sent_count = 0
    c.failed_count = 0
    c.delivered_count = 0
    c.read_count = 0
    c.product_label_filter = None
    c.append_seller_name = False
    c.append_seller_phone = False
    c.append_date = False
    c.seller_name = c.seller_phone = c.seller_phone2 = None
    c.emoji_level = "medium"
    for k, v in over.items():
        setattr(c, k, v)
    return c


def make_cc(contact, campaign, **over):
    cc = CampaignContact(campaign_id=campaign.id, contact_id=contact.id, status=MessageStatus.pending)
    cc.id = uuid.uuid4()
    cc.retry_count = 0
    cc.green_api_message_id = None
    cc.generated_message = None
    cc.sent_at = None
    cc.error_message = None
    cc.account_id = None
    cc.delivery_status = None
    for k, v in over.items():
        setattr(cc, k, v)
    return cc


# ══════════════════════════════════════════════════════════
# RATE LIMITER
# ══════════════════════════════════════════════════════════
def test_get_max_per_hour_in_window():
    from app.services import rate_limiter
    with patch.object(rate_limiter, "get_tehran_hour", return_value=10):
        assert rate_limiter.get_max_per_hour() == 200  # 10:00 slot


def test_get_max_per_hour_outside_window():
    from app.services import rate_limiter
    with patch.object(rate_limiter, "get_tehran_hour", return_value=3):
        assert rate_limiter.get_max_per_hour() == 0  # before 08:00


@pytest.mark.asyncio
async def test_get_max_per_hour_for_account_uses_schedule():
    from app.services import rate_limiter
    import app.database as database
    slot = MagicMock(max_per_hour=15)
    fake = FakeSession(results=[FakeResult(scalars=[slot])])
    with patch.object(rate_limiter, "get_tehran_hour", return_value=14), \
         patch.object(database, "AsyncSessionLocal", sessionmaker(fake)):
        # per-account slot wins over the global schedule
        assert await rate_limiter.get_max_per_hour_for_account(str(uuid.uuid4())) == 15


@pytest.mark.asyncio
async def test_get_max_per_hour_for_account_falls_back_global():
    from app.services import rate_limiter
    import app.database as database
    fake = FakeSession(results=[FakeResult(scalars=[])])  # no per-account slot
    with patch.object(rate_limiter, "get_tehran_hour", return_value=10), \
         patch.object(database, "AsyncSessionLocal", sessionmaker(fake)):
        assert await rate_limiter.get_max_per_hour_for_account(str(uuid.uuid4())) == 200


@pytest.mark.asyncio
async def test_can_send_blocked_when_window_closed():
    from app.services import rate_limiter
    with patch.object(rate_limiter, "get_max_per_hour_for_account", new=AsyncMock(return_value=0)):
        assert await rate_limiter.can_send(str(uuid.uuid4())) is False


@pytest.mark.asyncio
async def test_can_send_true_under_limit():
    from app.services import rate_limiter
    redis = MagicMock()
    redis.get = AsyncMock(return_value=b"3")
    with patch.object(rate_limiter, "get_max_per_hour_for_account", new=AsyncMock(return_value=10)), \
         patch.object(rate_limiter, "get_tehran_hour", return_value=12), \
         patch.object(rate_limiter, "redis_client", redis):
        assert await rate_limiter.can_send(str(uuid.uuid4())) is True


@pytest.mark.asyncio
async def test_can_send_false_at_limit():
    from app.services import rate_limiter
    redis = MagicMock()
    redis.get = AsyncMock(return_value=b"10")
    with patch.object(rate_limiter, "get_max_per_hour_for_account", new=AsyncMock(return_value=10)), \
         patch.object(rate_limiter, "get_tehran_hour", return_value=12), \
         patch.object(rate_limiter, "redis_client", redis):
        assert await rate_limiter.can_send(str(uuid.uuid4())) is False


@pytest.mark.asyncio
async def test_can_send_true_when_no_prior_count():
    from app.services import rate_limiter
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    with patch.object(rate_limiter, "get_max_per_hour_for_account", new=AsyncMock(return_value=10)), \
         patch.object(rate_limiter, "get_tehran_hour", return_value=12), \
         patch.object(rate_limiter, "redis_client", redis):
        assert await rate_limiter.can_send(str(uuid.uuid4())) is True


# ══════════════════════════════════════════════════════════
# WEBHOOK — handle_outgoing_status (delivery status)
# ══════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_handle_outgoing_status_delivered_updates_contact_and_counter():
    from app.api.v1 import webhook
    campaign = make_campaign()
    cc = make_cc(make_contact(), campaign, green_api_message_id="MID1")
    fake = FakeSession(results=[FakeResult(scalars=[cc])], gets={"Campaign": campaign})
    with patch.object(webhook, "AsyncSessionLocal", sessionmaker(fake)):
        await webhook.handle_outgoing_status("7105325764", {"idMessage": "MID1", "status": "delivered"})
    assert cc.delivery_status == "delivered"
    assert campaign.delivered_count == 1
    assert fake.commits == 1


@pytest.mark.asyncio
async def test_handle_outgoing_status_read_increments_read_count():
    from app.api.v1 import webhook
    campaign = make_campaign()
    cc = make_cc(make_contact(), campaign, green_api_message_id="MID2")
    fake = FakeSession(results=[FakeResult(scalars=[cc])], gets={"Campaign": campaign})
    with patch.object(webhook, "AsyncSessionLocal", sessionmaker(fake)):
        await webhook.handle_outgoing_status("7105325764", {"idMessage": "MID2", "status": "read"})
    assert cc.delivery_status == "read"
    assert campaign.read_count == 1


@pytest.mark.asyncio
async def test_handle_outgoing_status_no_matching_contact_is_noop():
    from app.api.v1 import webhook
    fake = FakeSession(results=[FakeResult(scalars=[])])  # no matching contact
    with patch.object(webhook, "AsyncSessionLocal", sessionmaker(fake)):
        await webhook.handle_outgoing_status("7105325764", {"idMessage": "UNKNOWN", "status": "read"})
    assert fake.commits == 0  # nothing to update → no commit


# ══════════════════════════════════════════════════════════
# WEBHOOK — handle_incoming (inbox + auto-reply + keyword)
# ══════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_handle_incoming_saves_inbox_autoreply_and_keyword():
    from app.api.v1 import webhook
    from app.models.inbox import InboxMessage
    account = make_account()
    fake = FakeSession(results=[FakeResult(scalars=[account])])

    payload = {
        "messageData": {"typeMessage": "textMessage", "textMessageData": {"textMessage": "سلام قیمت یخچال؟"}},
        "senderData": {"sender": "989123456789@c.us", "senderName": "رضا", "chatId": "989123456789@c.us", "chatName": ""},
        "timestamp": 1700000000,
        "idMessage": "IN1",
    }
    MockClient = MagicMock()
    client = MockClient.return_value
    client.send_message = AsyncMock(return_value="OUT1")
    client.send_group_message = AsyncMock(return_value="OUT1")

    with patch.object(webhook, "AsyncSessionLocal", sessionmaker(fake)), \
         patch("app.services.gpt_service.categorize_message", new=AsyncMock(return_value="price_inquiry")), \
         patch("app.services.auto_reply.process_auto_reply", new=AsyncMock(return_value=(True, "پاسخ خودکار"))), \
         patch("app.services.green_api.GreenAPIClient", MockClient), \
         patch("app.services.keyword_service.check_keywords", new=AsyncMock(return_value=(True, "پاسخ کلیدواژه", "rule-1", "pv"))), \
         patch("app.services.keyword_service.increment_use_count", new=AsyncMock()) as inc:
        await webhook.handle_incoming("7105325764", payload)

    # inbox message saved with parsed text + category
    inbox = [x for x in fake.added if isinstance(x, InboxMessage)]
    assert len(inbox) == 1
    assert inbox[0].text_content == "سلام قیمت یخچال؟"
    assert inbox[0].category == "price_inquiry"
    assert inbox[0].sender_phone == "989123456789"
    assert inbox[0].auto_replied is True
    # account counter bumped
    assert account.received_today == 1
    # both auto-reply and keyword replies sent (PV → send_message)
    assert client.send_message.await_count == 2
    inc.assert_awaited_once_with("rule-1")
    assert fake.commits >= 1


@pytest.mark.asyncio
async def test_handle_incoming_keyword_group_scope_replies_to_group():
    from app.api.v1 import webhook
    account = make_account()
    fake = FakeSession(results=[FakeResult(scalars=[account])])

    payload = {
        "messageData": {"typeMessage": "textMessage", "textMessageData": {"textMessage": "قیمت؟"}},
        "senderData": {"sender": "989123456789@c.us", "senderName": "علی",
                       "chatId": "120363111@g.us", "chatName": "گروه فروش"},
        "timestamp": 1700000000,
        "idMessage": "IN2",
    }
    MockClient = MagicMock()
    client = MockClient.return_value
    client.send_message = AsyncMock(return_value="X")
    client.send_group_message = AsyncMock(return_value="X")

    with patch.object(webhook, "AsyncSessionLocal", sessionmaker(fake)), \
         patch("app.services.gpt_service.categorize_message", new=AsyncMock(return_value="other")), \
         patch("app.services.auto_reply.process_auto_reply", new=AsyncMock(return_value=(False, None))), \
         patch("app.services.green_api.GreenAPIClient", MockClient), \
         patch("app.services.keyword_service.check_keywords", new=AsyncMock(return_value=(True, "پاسخ گروه", "rule-9", "group"))), \
         patch("app.services.keyword_service.increment_use_count", new=AsyncMock()), \
         patch("app.services.price_service.get_products", new=AsyncMock(return_value=[])):
        await webhook.handle_incoming("7105325764", payload)

    # group scope in a group → reply goes to the group chatId, not the sender
    client.send_group_message.assert_awaited_once_with("120363111@g.us", "پاسخ گروه")
    client.send_message.assert_not_awaited()


# ══════════════════════════════════════════════════════════
# CAMPAIGN RUNNER — send flow
# ══════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_run_campaign_sends_updates_status_and_counter():
    from app.services import campaign_runner, rate_limiter, delay_service
    from app.models.reporting import DailySendLog

    account = make_account()
    contact = make_contact()
    campaign = make_campaign()
    cc = make_cc(contact, campaign)

    fake = FakeSession(
        results=[
            FakeResult(rows=[(cc, contact)]),   # pending contacts
            FakeResult(scalars=[account]),      # active accounts
            FakeResult(scalars=[]),             # remaining pending → complete
        ],
        gets={"Campaign": campaign},
    )
    MockClient = MagicMock()
    client = MockClient.return_value
    client.send_message = AsyncMock(return_value="MSG-OK")
    client.send_typing = AsyncMock(return_value=True)
    rec_send = AsyncMock()

    with patch.object(campaign_runner, "AsyncSessionLocal", sessionmaker(fake)), \
         patch.object(campaign_runner, "GreenAPIClient", MockClient), \
         patch.object(campaign_runner, "can_send", new=AsyncMock(return_value=True)), \
         patch.object(campaign_runner, "record_send", new=rec_send), \
         patch.object(campaign_runner.asyncio, "sleep", new=AsyncMock()), \
         patch.object(rate_limiter, "get_max_per_hour_for_account", new=AsyncMock(return_value=50)), \
         patch.object(rate_limiter, "seconds_until_account_window", new=AsyncMock(return_value=0)), \
         patch.object(rate_limiter, "get_hour_prompt_for_account", new=AsyncMock(return_value=(None, None, False))), \
         patch.object(delay_service, "get_delay", new=AsyncMock(return_value=(0, 0))):
        await campaign_runner.run_campaign(str(campaign.id))

    # message actually sent to the contact
    client.send_message.assert_awaited_once()
    args = client.send_message.await_args.args
    assert args[0] == contact.phone
    assert "رضا" in args[1]  # template rendered {{first_name}}
    # contact + campaign state updated
    assert cc.status == MessageStatus.sent
    assert cc.green_api_message_id == "MSG-OK"
    assert account.sent_today == 1           # daily counter incremented
    assert campaign.sent_count == 1
    assert campaign.status == CampaignStatus.completed
    rec_send.assert_awaited_once()
    # daily send log written (night report source)
    logs = [x for x in fake.added if isinstance(x, DailySendLog)]
    assert len(logs) == 1 and logs[0].status == "sent"


@pytest.mark.asyncio
async def test_run_campaign_no_active_account_pauses():
    from app.services import campaign_runner
    from app.services.campaign_runner import NO_ACCOUNT_REASON

    contact = make_contact()
    campaign = make_campaign()
    cc = make_cc(contact, campaign)

    fake = FakeSession(
        results=[
            FakeResult(rows=[(cc, contact)]),   # pending contacts
            FakeResult(scalars=[]),             # NO active accounts
        ],
        gets={"Campaign": campaign},
    )
    MockClient = MagicMock()
    client = MockClient.return_value
    client.send_message = AsyncMock()

    with patch.object(campaign_runner, "AsyncSessionLocal", sessionmaker(fake)), \
         patch.object(campaign_runner, "GreenAPIClient", MockClient):
        await campaign_runner.run_campaign(str(campaign.id))

    assert campaign.status == CampaignStatus.paused
    assert campaign.pause_reason == NO_ACCOUNT_REASON
    client.send_message.assert_not_awaited()
