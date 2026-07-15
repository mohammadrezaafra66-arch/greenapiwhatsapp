"""V18 PART 2 — warm-up toggle → V17 mesh + enrollment-based campaign exclusion.

Covers: the exclusion authority (active-warming excluded, GRADUATED eligible, legacy
fallback), the toggle endpoint creating a real enrollment (not just a boolean) and
kicking pre-flight, and an integration test proving a mesh-warming account is dropped from
a campaign's eligible set (combining with PART 1's fail-closed selection).
"""
import uuid
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.warmup_exclusion import (
    warmup_campaign_excluded, active_warming_instance_ids, enrolled_instance_ids,
    enrollment_states_by_instance, GRADUATED,
)
from app.services.warmup_state import WarmupState


def _acc(instance_id, auto_warmup=False, warmup_completed=False):
    return SimpleNamespace(instance_id=instance_id, auto_warmup=auto_warmup,
                           warmup_completed=warmup_completed)


# ── warmup_campaign_excluded (the exclusion authority) ──────────────────────
def test_active_warming_is_excluded():
    enr = {"NEW": (WarmupState.RAMPING.value, True)}
    assert warmup_campaign_excluded(_acc("NEW"), enr) is True
    assert warmup_campaign_excluded(_acc("NEW"), {"NEW": (WarmupState.COOLDOWN.value, True)}) is True
    assert warmup_campaign_excluded(_acc("NEW"), {"NEW": (WarmupState.RECEIVING.value, True)}) is True


def test_graduated_is_eligible_even_with_legacy_flag():
    enr = {"NEW": (GRADUATED, True)}
    # graduated overrides even a stale auto_warmup=True
    assert warmup_campaign_excluded(_acc("NEW", auto_warmup=True), enr) is False


def test_disabled_enrollment_is_eligible():
    enr = {"NEW": (WarmupState.PAUSED.value, False)}
    assert warmup_campaign_excluded(_acc("NEW"), enr) is False


def test_no_enrollment_falls_back_to_legacy_flag():
    # no enrollment row → legacy in_active_warmup(auto_warmup & not completed)
    assert warmup_campaign_excluded(_acc("OLD", auto_warmup=True), {}) is True
    assert warmup_campaign_excluded(_acc("OLD", auto_warmup=False), {}) is False
    assert warmup_campaign_excluded(_acc("OLD", auto_warmup=True, warmup_completed=True), {}) is False


# ── FakeSession supporting .all() rows for the enrollment map query ──────────
class FakeAllResult:
    def __init__(self, rows): self._rows = rows
    def all(self): return list(self._rows)


class FakeSession:
    def __init__(self, results=None, gets=None):
        self._results = list(results or [])
        self._gets = dict(gets or {})
        self.added = []; self.commits = 0
    async def get(self, model, pk): return self._gets.get(model.__name__)
    async def execute(self, q): return self._results.pop(0) if self._results else FakeAllResult([])
    def add(self, o): self.added.append(o)
    async def commit(self): self.commits += 1
    async def refresh(self, o): pass
    async def flush(self): pass


@pytest.mark.asyncio
async def test_enrollment_map_and_warming_ids():
    rows = [("A", WarmupState.RAMPING.value, True),
            ("B", GRADUATED, True),
            ("C", WarmupState.PAUSED.value, False)]
    m = await enrollment_states_by_instance(FakeSession(results=[FakeAllResult(rows)]))
    assert m == {"A": (WarmupState.RAMPING.value, True), "B": (GRADUATED, True), "C": (WarmupState.PAUSED.value, False)}
    warming = await active_warming_instance_ids(FakeSession(results=[FakeAllResult(rows)]))
    assert warming == {"A"}                       # only active + non-graduated
    enrolled = await enrolled_instance_ids(FakeSession(results=[FakeAllResult(rows)]))
    assert enrolled == {"A", "B", "C"}


@pytest.mark.asyncio
async def test_enrollment_map_failsafe_on_error():
    class BadDB:
        async def execute(self, q): raise RuntimeError("table missing")
    assert await enrollment_states_by_instance(BadDB()) == {}   # never breaks campaigns


# ── toggle endpoint drives V17 (creates a real enrollment) ──────────────────
@pytest.mark.asyncio
async def test_toggle_on_calls_enroll_and_preflight():
    from app.api.v1 import accounts as accounts_api
    from app.models.account import Account, AccountStatus
    acc = Account(name="n", instance_id="NEW", api_token="t"); acc.id = uuid.uuid4()
    acc.status = AccountStatus.active; acc.auto_warmup = True
    db = FakeSession(gets={"Account": acc})

    enroll_mock = AsyncMock(return_value={"state": "COOLDOWN", "notice": None,
                                          "peers": [{"peer_instance_id": "P1"}],
                                          "cooldown_hours": 24.0, "settings_applied": True})
    with patch.object(accounts_api, "_get_account", new=AsyncMock(return_value=acc)), \
         patch("app.services.warmup_mesh_service.enroll_and_preflight", new=enroll_mock):
        res = await accounts_api.set_auto_warmup(str(acc.id), accounts_api.WarmupToggle(enabled=True), db)

    enroll_mock.assert_awaited_once()             # V17 pre-flight kicked off
    assert res["warmup_enrolled"] is True
    assert res["state"] == "COOLDOWN"
    assert acc.auto_warmup is False               # migrated off the legacy flag


@pytest.mark.asyncio
async def test_toggle_off_disables_enrollment():
    from app.api.v1 import accounts as accounts_api
    from app.models.account import Account, AccountStatus
    acc = Account(name="n", instance_id="NEW", api_token="t"); acc.id = uuid.uuid4()
    acc.status = AccountStatus.active; acc.auto_warmup = True
    db = FakeSession(gets={"Account": acc})
    disable_mock = AsyncMock(return_value={"state": "PAUSED", "disabled": True})
    with patch.object(accounts_api, "_get_account", new=AsyncMock(return_value=acc)), \
         patch("app.services.warmup_mesh_service.disable_warmup", new=disable_mock):
        res = await accounts_api.set_auto_warmup(str(acc.id), accounts_api.WarmupToggle(enabled=False), db)
    disable_mock.assert_awaited_once()
    assert res["warmup_enrolled"] is False
    assert acc.auto_warmup is False


@pytest.mark.asyncio
async def test_toggle_on_insufficient_peers_surfaces_notice():
    from app.api.v1 import accounts as accounts_api
    from app.models.account import Account, AccountStatus
    from app.services.warmup_mesh_service import INSUFFICIENT_PEERS_NOTICE
    acc = Account(name="n", instance_id="NEW", api_token="t"); acc.id = uuid.uuid4()
    acc.status = AccountStatus.active; acc.auto_warmup = False
    db = FakeSession(gets={"Account": acc})
    enroll_mock = AsyncMock(return_value={"state": "COOLDOWN", "notice": INSUFFICIENT_PEERS_NOTICE,
                                          "peers": [], "cooldown_hours": 24.0, "settings_applied": True})
    with patch.object(accounts_api, "_get_account", new=AsyncMock(return_value=acc)), \
         patch("app.services.warmup_mesh_service.enroll_and_preflight", new=enroll_mock):
        res = await accounts_api.set_auto_warmup(str(acc.id), accounts_api.WarmupToggle(enabled=True), db)
    assert res["notice"] == INSUFFICIENT_PEERS_NOTICE and res["peers"] == []


# ── integration: a mesh-warming account is dropped from campaign eligibility ─
class FR:
    def __init__(self, rows=None, scalars=None, all_rows=None):
        self._rows = rows or []; self._scalars = scalars if scalars is not None else []
        self._all = all_rows
    def all(self): return list(self._all) if self._all is not None else list(self._rows)
    def scalars(self):
        outer = self
        class S:
            def all(self_inner): return list(outer._scalars)
            def first(self_inner): return outer._scalars[0] if outer._scalars else None
        return S()
    def scalar_one_or_none(self): return self._scalars[0] if self._scalars else None


class IntSession:
    def __init__(self, results, gets):
        self._results = list(results); self._gets = dict(gets); self.added=[]; self.commits=0
    async def get(self, m, pk): return self._gets.get(m.__name__)
    async def execute(self, q): return self._results.pop(0) if self._results else FR()
    def add(self, o): self.added.append(o)
    async def commit(self): self.commits += 1
    async def refresh(self, o): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


@pytest.mark.asyncio
async def test_warming_account_excluded_from_campaign_and_aborts_when_selected():
    """User selects a number that is being mesh-warmed → it's excluded → fail-closed abort
    (never sends). Combines PART 2 exclusion with PART 1 fail-closed selection."""
    from app.services import campaign_runner
    from app.services.account_selection import SELECTED_ACCOUNT_UNAVAILABLE_REASON
    from app.models.account import Account, AccountStatus
    from app.models.campaign import Campaign, CampaignContact, CampaignStatus, CampaignType, MessageStatus
    from app.models.contact import Contact

    W = Account(name="W", instance_id="WARM", api_token="t"); W.id = uuid.uuid4(); W.status = AccountStatus.active
    camp = Campaign(name="c"); camp.id = uuid.uuid4(); camp.status = CampaignStatus.running
    camp.campaign_type = CampaignType.text; camp.schedule_start = camp.schedule_end = None
    camp.parallel_accounts = False; camp.selected_account_id = W.id; camp.pause_reason = None

    contact = Contact(phone="989120000000"); contact.id = uuid.uuid4()
    contact.blacklisted = False; contact.has_whatsapp = None
    cc = CampaignContact(campaign_id=camp.id, contact_id=contact.id, status=MessageStatus.pending); cc.id = uuid.uuid4()

    # enrollment map query returns WARM as actively RAMPING → excluded
    enr_rows = [("WARM", WarmupState.RAMPING.value, True)]
    fake = IntSession(
        results=[FR(rows=[(cc, contact)]),          # pending
                 FR(scalars=[W]),                    # active accounts
                 FR(all_rows=enr_rows)],             # enrollment map
        gets={"Campaign": camp},
    )
    MockClient = MagicMock(); MockClient.return_value.send_message = AsyncMock(return_value="MID")
    with patch.object(campaign_runner, "AsyncSessionLocal", lambda: fake), \
         patch.object(campaign_runner, "GreenAPIClient", MockClient), \
         patch("app.services.governors.in_cooldown", return_value=False):
        await campaign_runner.run_campaign(str(camp.id))

    assert camp.status == CampaignStatus.paused
    assert camp.pause_reason == SELECTED_ACCOUNT_UNAVAILABLE_REASON   # warming → not eligible → abort
    MockClient.return_value.send_message.assert_not_awaited()          # nothing sent
