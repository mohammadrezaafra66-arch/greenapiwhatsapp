"""V50 PART 2 — scheduled automatic story fetch (Celery beat).

Proves:
  • the new beat entry is registered at the chosen conservative 30-min (1800s) cadence and points
    at tasks.fetch_incoming_stories;
  • the task exists and is a registered Celery task;
  • triggering the task drives PART 1's fetch_stories_for_all_eligible_accounts (the multi-account
    path), not some duplicated logic;
  • the manual on-page refresh path is untouched — the /statuses/incoming endpoint still fetches
    immediately via the same client + persist path (regression guard).
"""
import inspect

import pytest

from app.workers.celery_app import celery_app
from app.workers import tasks as tasks_mod


def test_beat_entry_registered_at_30min():
    sched = celery_app.conf.beat_schedule
    assert "fetch-incoming-stories" in sched
    entry = sched["fetch-incoming-stories"]
    assert entry["task"] == "tasks.fetch_incoming_stories"
    # Conservative cadence (guardrail 4) — 30 minutes, NOT aggressive polling.
    assert entry["schedule"] == 1800.0


def test_task_is_registered_in_celery():
    assert "tasks.fetch_incoming_stories" in celery_app.tasks
    assert hasattr(tasks_mod, "task_fetch_incoming_stories")


def test_task_calls_part1_multi_account_fetch(monkeypatch):
    """The scheduled task must delegate to PART 1's multi-account function (with a real DB
    session), not fetch from a single hardcoded account."""
    called = {"count": 0}

    class _FakeSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    def _fake_session_factory():
        return _FakeSession()

    async def _fake_fetch_all(db, **kwargs):
        called["count"] += 1
        called["db"] = db
        return {"eligible": 2, "fetched": 2, "failed": 0, "skipped": 1, "total_statuses": 7}

    monkeypatch.setattr("app.database.AsyncSessionLocal", _fake_session_factory)
    monkeypatch.setattr(
        "app.services.story_fetch.fetch_stories_for_all_eligible_accounts", _fake_fetch_all)

    # Call the task body synchronously (run_async drives the inner coroutine to completion).
    tasks_mod.task_fetch_incoming_stories()

    assert called["count"] == 1
    assert isinstance(called["db"], _FakeSession)


def test_manual_refresh_endpoint_unchanged():
    """Regression: the manual /statuses/incoming handler still performs an IMMEDIATE fetch via the
    same client.get_incoming_statuses + _persist_incoming path — the scheduled task is additive,
    not a replacement."""
    from app.api.v1 import statuses as statuses_api
    src = inspect.getsource(statuses_api.incoming_statuses)
    assert "get_incoming_statuses" in src
    assert "_persist_incoming" in src


def test_scheduled_task_reuses_the_same_service_as_part1():
    """The task imports PART 1's function by name — a single source of truth, no duplicated loop."""
    src = inspect.getsource(tasks_mod.task_fetch_incoming_stories)
    assert "fetch_stories_for_all_eligible_accounts" in src
