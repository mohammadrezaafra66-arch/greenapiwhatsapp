"""V18 PART 1 — fail-closed account selection (no silent multi-account fan-out).

Unit-tests the selection resolver + the hard subset invariant, plus an integration test
proving that a campaign whose single selected account is filtered out ABORTS (Persian
reason) and sends from NOTHING — it never fans out to the other accounts.
"""
import uuid
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.account_selection import (
    selected_account_ids, filter_to_selection, assert_sending_subset,
    resolve_sending_accounts, FanOutGuardError,
    NO_ACCOUNT_REASON, SELECTED_ACCOUNT_UNAVAILABLE_REASON,
)


def _acc(**kw):
    a = SimpleNamespace(id=uuid.uuid4(), instance_id=kw.get("instance_id", "i"))
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def _camp(parallel=False, selected=None):
    return SimpleNamespace(parallel_accounts=parallel, selected_account_id=selected)


# ── selected_account_ids ─────────────────────────────────────────────────────
def test_selected_ids_single():
    a = _acc()
    assert selected_account_ids(_camp(selected=a.id)) == {a.id}


def test_selected_ids_parallel_is_none():
    assert selected_account_ids(_camp(parallel=True, selected=uuid.uuid4())) is None


def test_selected_ids_none_when_nothing_picked():
    assert selected_account_ids(_camp()) is None


# ── filter_to_selection ──────────────────────────────────────────────────────
def test_filter_none_allows_all():
    a, b = _acc(), _acc()
    assert filter_to_selection([a, b], None) == [a, b]


def test_filter_intersects_selection():
    a, b, c = _acc(), _acc(), _acc()
    got = filter_to_selection([a, b, c], {a.id, c.id})
    assert got == [a, c]


def test_filter_multiple_selected_some_ineligible():
    """Multiple selected, one filtered out of eligible → only the eligible selected subset."""
    a, b, c = _acc(), _acc(), _acc()
    eligible = [a, c]                       # b was filtered out upstream
    assert filter_to_selection(eligible, {a.id, b.id}) == [a]


# ── assert_sending_subset (the hard invariant) ──────────────────────────────
def test_assert_subset_passes_for_subset():
    a, b = _acc(), _acc()
    assert assert_sending_subset([a], {a.id, b.id}) == [a]


def test_assert_subset_none_selection_is_noop():
    a = _acc()
    assert assert_sending_subset([a], None) == [a]


def test_assert_subset_raises_on_escape():
    a, b = _acc(), _acc()
    with pytest.raises(FanOutGuardError):
        assert_sending_subset([a, b], {a.id})   # b escaped the selection


# ── resolve_sending_accounts (fail-closed) ──────────────────────────────────
def test_resolve_single_selected_eligible():
    a, b = _acc(), _acc()
    accts, reason = resolve_sending_accounts([a, b], _camp(selected=a.id))
    assert accts == [a] and reason is None          # only the selected one, never b


def test_resolve_single_selected_filtered_out_aborts():
    a, b = _acc(), _acc()
    # a (selected) is NOT in the eligible set → must abort, NOT fall back to b
    accts, reason = resolve_sending_accounts([b], _camp(selected=a.id))
    assert accts == [] and reason == SELECTED_ACCOUNT_UNAVAILABLE_REASON


def test_resolve_no_selection_uses_all_eligible():
    a, b = _acc(), _acc()
    accts, reason = resolve_sending_accounts([a, b], _camp())
    assert accts == [a, b] and reason is None


def test_resolve_no_selection_empty_eligible():
    accts, reason = resolve_sending_accounts([], _camp())
    assert accts == [] and reason == NO_ACCOUNT_REASON


def test_resolve_parallel_uses_all_eligible():
    a, b = _acc(), _acc()
    accts, reason = resolve_sending_accounts([a, b], _camp(parallel=True))
    assert accts == [a, b] and reason is None


# ══════════════════════════ integration: no fan-out ══════════════════════════
class FakeScalars:
    def __init__(self, items): self._items = list(items)
    def all(self): return list(self._items)
    def first(self): return self._items[0] if self._items else None


class FakeResult:
    def __init__(self, rows=None, scalars=None):
        self._rows = rows or []
        self._scalars = scalars if scalars is not None else []
    def all(self): return list(self._rows)
    def scalars(self): return FakeScalars(self._scalars)
    def scalar_one_or_none(self): return self._scalars[0] if self._scalars else None


class FakeSession:
    def __init__(self, results=None, gets=None):
        self._results = list(results or [])
        self._gets = dict(gets or {})
        self.added = []; self.commits = 0
    async def get(self, model, pk): return self._gets.get(model.__name__)
    async def execute(self, q): return self._results.pop(0) if self._results else FakeResult()
    def add(self, o): self.added.append(o)
    async def commit(self): self.commits += 1
    async def refresh(self, o): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


def _sessionmaker(s): return lambda: s


@pytest.mark.asyncio
async def test_selected_account_ineligible_aborts_and_does_not_fan_out():
    from app.services import campaign_runner
    from app.models.account import Account, AccountStatus
    from app.models.campaign import Campaign, CampaignContact, CampaignStatus, CampaignType, MessageStatus
    from app.models.contact import Contact

    X = Account(name="X", instance_id="X1", api_token="t"); X.id = uuid.uuid4(); X.status = AccountStatus.active
    Y = Account(name="Y", instance_id="Y1", api_token="t"); Y.id = uuid.uuid4(); Y.status = AccountStatus.active

    camp = Campaign(name="c"); camp.id = uuid.uuid4()
    camp.status = CampaignStatus.running; camp.campaign_type = CampaignType.text
    camp.schedule_start = camp.schedule_end = None
    camp.parallel_accounts = False; camp.selected_account_id = X.id     # user picked X only
    camp.pause_reason = None; camp.include_products = False; camp.poll_options = None
    camp.button1_text = camp.button2_text = camp.button3_text = None

    contact = Contact(phone="989120000000"); contact.id = uuid.uuid4()
    contact.blacklisted = False; contact.has_whatsapp = None
    cc = CampaignContact(campaign_id=camp.id, contact_id=contact.id, status=MessageStatus.pending)
    cc.id = uuid.uuid4()

    fake = FakeSession(
        results=[FakeResult(rows=[(cc, contact)]),   # pending contacts
                 FakeResult(scalars=[X, Y])],         # active accounts
        gets={"Campaign": camp},
    )
    MockClient = MagicMock(); client = MockClient.return_value
    client.send_message = AsyncMock(return_value="MID")

    with patch.object(campaign_runner, "AsyncSessionLocal", _sessionmaker(fake)), \
         patch.object(campaign_runner, "GreenAPIClient", MockClient), \
         patch("app.services.governors.in_cooldown", side_effect=lambda a, now=None: a.id == X.id), \
         patch("app.services.warmup_auto.in_active_warmup", return_value=False):
        await campaign_runner.run_campaign(str(camp.id))

    # X (selected) was filtered out → campaign ABORTS with the Persian reason…
    assert camp.status == CampaignStatus.paused
    assert camp.pause_reason == SELECTED_ACCOUNT_UNAVAILABLE_REASON
    # …and NOTHING was sent — crucially NOT from Y (no silent fan-out).
    client.send_message.assert_not_awaited()
