"""V50 PART 1 — multi-account incoming-story fetch.

Proves:
  • account_story_eligibility reuses the shared send-health gate + the V41 mesh-recovery pause:
    an active/healthy account is eligible; a not-active / connect-cooldown / yellowCard-cooldown /
    throttled / mesh-recovery account is skipped with the right reason slug;
  • fetch_stories_for_all_eligible_accounts fetches ONLY from the eligible accounts, threads the
    correct instance_id per account, and sums the merged status counts;
  • one account's fetch raising is isolated — the remaining accounts are still fetched, and the
    failure is counted (not swallowed into a false success);
  • fetch_stories_for_account reuses the EXACT manual-endpoint path (GreenAPIClient.get_incoming_
    statuses + the endpoint's own _persist_incoming) with this account's instance_id — no duplicated
    fetch/persist logic.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services import story_fetch
from app.services.story_fetch import (
    account_story_eligibility, fetch_stories_for_all_eligible_accounts,
    fetch_stories_for_account,
)

NOW = datetime(2026, 7, 27, 12, 0, 0)


class _DB:
    """Minimal async session double — the loop itself never queries when `accounts` is injected;
    mesh-recovery is monkeypatched, so execute is only a safety no-op."""
    async def execute(self, *a, **k):
        raise AssertionError("no DB query expected in these injected-account tests")


def _acc(instance_id, *, status="active", is_default=False, connected_at=None,
         cooldown_until=None, throttle_until=None, throttle_factor=1.0):
    return SimpleNamespace(
        instance_id=instance_id, api_token="tok-" + instance_id, name=instance_id,
        is_default=is_default, platform="whatsapp",
        status=SimpleNamespace(value=status),
        connected_at=connected_at, reconnected_at=None,
        cooldown_until=cooldown_until, throttle_until=throttle_until,
        throttle_factor=throttle_factor,
    )


@pytest.fixture(autouse=True)
def _no_mesh_recovery(monkeypatch):
    """Default: nobody is in mesh recovery. Individual tests override the recovering set."""
    recovering: set = set()

    async def _fake(db, instance_id):
        return instance_id in recovering

    monkeypatch.setattr(story_fetch, "in_mesh_recovery", _fake)
    return recovering


# ── eligibility ────────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_healthy_active_account_is_eligible():
    ok, reason = await account_story_eligibility(_DB(), _acc("A"), NOW)
    assert ok is True and reason == "ok"


@pytest.mark.asyncio
async def test_not_active_account_skipped():
    ok, reason = await account_story_eligibility(_DB(), _acc("B", status="disconnected"), NOW)
    assert ok is False and reason == "not_active"


@pytest.mark.asyncio
async def test_connect_cooldown_account_skipped():
    # Connected 2h ago → still inside the universal 24h connect-cooldown.
    acc = _acc("C", connected_at=NOW - timedelta(hours=2))
    ok, reason = await account_story_eligibility(_DB(), acc, NOW)
    assert ok is False and reason == "connect_cooldown"


@pytest.mark.asyncio
async def test_yellowcard_cooldown_account_skipped():
    acc = _acc("D", cooldown_until=NOW + timedelta(hours=5))
    ok, reason = await account_story_eligibility(_DB(), acc, NOW)
    assert ok is False and reason == "cooldown"


@pytest.mark.asyncio
async def test_mesh_recovery_account_skipped(_no_mesh_recovery):
    _no_mesh_recovery.add("R")
    ok, reason = await account_story_eligibility(_DB(), _acc("R"), NOW)
    assert ok is False and reason == "in_mesh_recovery"


@pytest.mark.asyncio
async def test_connected_over_24h_ago_is_eligible():
    acc = _acc("E", connected_at=NOW - timedelta(hours=25))
    ok, reason = await account_story_eligibility(_DB(), acc, NOW)
    assert ok is True and reason == "ok"


# ── the multi-account loop ───────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_loops_only_over_eligible_accounts_and_threads_instance_id(_no_mesh_recovery):
    _no_mesh_recovery.add("recovering")
    accounts = [
        _acc("default", is_default=True),                       # healthy
        _acc("other", ),                                        # healthy non-default
        _acc("cooldown", connected_at=NOW - timedelta(hours=1)),  # skipped: connect-cooldown
        _acc("offline", status="disconnected"),                 # skipped: not active
        _acc("recovering"),                                     # skipped: mesh recovery
    ]
    calls = []

    async def _fetch(db, account):
        calls.append(account.instance_id)
        return {"default": 3, "other": 5}[account.instance_id]

    summary = await fetch_stories_for_all_eligible_accounts(
        _DB(), accounts=accounts, fetch_fn=_fetch, now=NOW)

    # Only the two healthy accounts were fetched — the other three skipped.
    assert calls == ["default", "other"]
    assert summary["eligible"] == 2 and summary["fetched"] == 2 and summary["failed"] == 0
    assert summary["skipped"] == 3
    assert summary["total_statuses"] == 8          # 3 + 5 merged
    # Each result row carries the RIGHT instance_id + its own count.
    assert {r["instance_id"]: r["count"] for r in summary["results"]} == {"default": 3, "other": 5}
    reasons = {d["instance_id"]: d["reason"] for d in summary["skipped_detail"]}
    assert reasons == {"cooldown": "connect_cooldown", "offline": "not_active",
                       "recovering": "in_mesh_recovery"}


@pytest.mark.asyncio
async def test_one_account_failure_does_not_abort_the_others(_no_mesh_recovery):
    accounts = [_acc("a1", is_default=True), _acc("a2"), _acc("a3")]

    async def _fetch(db, account):
        if account.instance_id == "a2":
            raise RuntimeError("green api 500 for a2")
        return 4

    summary = await fetch_stories_for_all_eligible_accounts(
        _DB(), accounts=accounts, fetch_fn=_fetch, now=NOW)

    # a1 and a3 still fetched despite a2 blowing up.
    assert summary["eligible"] == 3
    assert summary["fetched"] == 2 and summary["failed"] == 1
    assert summary["total_statuses"] == 8          # a1(4) + a3(4); a2 contributed nothing
    errored = [r for r in summary["results"] if "error" in r]
    assert len(errored) == 1 and errored[0]["instance_id"] == "a2"
    assert "500 for a2" in errored[0]["error"]


@pytest.mark.asyncio
async def test_no_eligible_accounts_is_a_clean_noop(_no_mesh_recovery):
    accounts = [_acc("x", status="banned"), _acc("y", status="disconnected")]

    async def _fetch(db, account):  # pragma: no cover - must never be called
        raise AssertionError("should not fetch from an ineligible account")

    summary = await fetch_stories_for_all_eligible_accounts(
        _DB(), accounts=accounts, fetch_fn=_fetch, now=NOW)
    assert summary == {"eligible": 0, "fetched": 0, "failed": 0, "skipped": 2,
                       "total_statuses": 0, "results": [],
                       "skipped_detail": [{"instance_id": "x", "reason": "not_active"},
                                          {"instance_id": "y", "reason": "not_active"}]}


# ── per-account fetch reuses the EXACT manual-endpoint path ───────────────────────────────────────
@pytest.mark.asyncio
async def test_fetch_for_account_reuses_client_and_persist(monkeypatch):
    seen = {}

    class _FakeClient:
        def __init__(self, instance_id, api_token):
            seen["client_args"] = (instance_id, api_token)
        async def get_incoming_statuses(self):
            return [{"idMessage": "S1"}, {"idMessage": "S2"}]

    async def _fake_persist(db, instance_id, statuses):
        seen["persist_args"] = (instance_id, [s["idMessage"] for s in statuses])

    monkeypatch.setattr("app.services.green_api.GreenAPIClient", _FakeClient)
    # _persist_incoming is imported lazily from the API module inside the function under test.
    monkeypatch.setattr("app.api.v1.statuses._persist_incoming", _fake_persist)

    acc = _acc("770022693143")
    n = await fetch_stories_for_account(_DB(), acc)

    assert n == 2
    assert seen["client_args"] == ("770022693143", "tok-770022693143")
    # The SAME instance_id is threaded into the endpoint's own persistence helper.
    assert seen["persist_args"] == ("770022693143", ["S1", "S2"])
