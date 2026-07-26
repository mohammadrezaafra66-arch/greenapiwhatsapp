"""V50 PART 3 — final end-to-end simulation of the scheduled multi-account story fetch.

Scenario (mirrors the real fleet): the primary default account is healthy, three other accounts
are healthy and connected, one account is mid mesh-recovery (must be excluded), and one is offline.
A scheduled run (no page visit) must fetch from ALL FOUR eligible accounts and merge every fetched
status into the shared received_statuses store keyed per-row by instance_id — while contributing
NOTHING from the recovering or offline accounts.

This is the resilience+coverage guarantee end-to-end: stories now arrive from multiple accounts
automatically, so the fleet no longer depends on a single default account being online AND a human
opening the page.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services import story_fetch
from app.services.story_fetch import fetch_stories_for_all_eligible_accounts

NOW = datetime(2026, 7, 27, 12, 0, 0)


class _DB:
    async def execute(self, *a, **k):
        raise AssertionError("injected-account e2e path should not query the DB directly")


def _acc(instance_id, *, status="active", is_default=False, connected_at=None):
    return SimpleNamespace(
        instance_id=instance_id, api_token="tok-" + instance_id, name=instance_id,
        is_default=is_default, platform="whatsapp",
        status=SimpleNamespace(value=status),
        connected_at=connected_at, reconnected_at=None,
        cooldown_until=None, throttle_until=None, throttle_factor=1.0,
    )


@pytest.mark.asyncio
async def test_scheduled_run_fetches_all_eligible_and_merges(monkeypatch):
    recovering = {"770022693145"}

    async def _fake_mesh(db, instance_id):
        return instance_id in recovering

    monkeypatch.setattr(story_fetch, "in_mesh_recovery", _fake_mesh)

    # The real fleet shape: 1 default healthy + 3 other healthy + 1 recovering + 1 offline.
    accounts = [
        _acc("7105325764", is_default=True),                       # primary default, healthy
        _acc("770022693142"),                                      # other healthy
        _acc("770022693143"),                                      # other healthy
        _acc("770022693144"),                                      # other healthy
        _acc("770022693145"),                                      # mesh recovery -> excluded
        _acc("770022683838", status="disconnected"),               # offline -> excluded
    ]

    # A shared store standing in for received_statuses: each fetched row carries its instance_id,
    # exactly as the real per-row `instance_id` column does. Simulated per-account payload sizes.
    store: list[dict] = []
    payloads = {"7105325764": 6, "770022693142": 2, "770022693143": 4, "770022693144": 1}

    async def _fetch(db, account):
        n = payloads[account.instance_id]
        for i in range(n):
            store.append({"instance_id": account.instance_id, "msg": f"{account.instance_id}-{i}"})
        return n

    summary = await fetch_stories_for_all_eligible_accounts(
        _DB(), accounts=accounts, fetch_fn=_fetch, now=NOW)

    # All four eligible accounts fetched; the two ineligible ones skipped with the right reasons.
    assert summary["eligible"] == 4 and summary["fetched"] == 4 and summary["failed"] == 0
    assert summary["skipped"] == 2
    assert summary["total_statuses"] == 13                         # 6+2+4+1
    reasons = {d["instance_id"]: d["reason"] for d in summary["skipped_detail"]}
    assert reasons == {"770022693145": "in_mesh_recovery", "770022683838": "not_active"}

    # The merged store carries rows from every eligible account (incl. NON-default ones) and none
    # from the excluded accounts — proving multi-account coverage without any page visit.
    by_instance = {}
    for row in store:
        by_instance.setdefault(row["instance_id"], 0)
        by_instance[row["instance_id"]] += 1
    assert by_instance == {"7105325764": 6, "770022693142": 2,
                           "770022693143": 4, "770022693144": 1}
    # At least one NON-default account contributed — the core resilience win.
    assert by_instance.get("770022693142", 0) > 0
    assert "770022693145" not in by_instance and "770022683838" not in by_instance


@pytest.mark.asyncio
async def test_default_account_offline_still_fetches_from_others(monkeypatch):
    """The exact failure the diagnostic found: even if the single default account is DOWN, the
    other healthy accounts now still fetch stories — zero-fallback is fixed."""
    async def _no_mesh(db, instance_id):
        return False

    monkeypatch.setattr(story_fetch, "in_mesh_recovery", _no_mesh)

    accounts = [
        _acc("7105325764", is_default=True, status="disconnected"),   # the historical sole source, DOWN
        _acc("770022693142"),
        _acc("770022693143"),
    ]

    async def _fetch(db, account):
        return 5

    summary = await fetch_stories_for_all_eligible_accounts(
        _DB(), accounts=accounts, fetch_fn=_fetch, now=NOW)

    assert summary["fetched"] == 2 and summary["total_statuses"] == 10
    fetched_ids = {r["instance_id"] for r in summary["results"] if "count" in r}
    assert fetched_ids == {"770022693142", "770022693143"}
    assert summary["skipped_detail"] == [{"instance_id": "7105325764", "reason": "not_active"}]
