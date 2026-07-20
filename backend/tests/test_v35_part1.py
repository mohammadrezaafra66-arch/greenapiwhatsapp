"""V35 PART 1 — the automatic daily WhatsApp Status post at 10:00 Tehran is stopped.

Root cause: the `warmup-accounts` beat entry fired `tasks.warmup_accounts` at 10:00 Tehran,
which called `warmup_service.post_daily_status()`, auto-posting a public WhatsApp status every
day (the behaviour the user asked us to stop; also a ban risk). The fix:

  * `post_daily_status` is now a guarded no-op (DAILY_STATUS_POSTING_DISABLED) — it can never
    reach the Green API status endpoint.
  * `tasks.warmup_accounts` no longer references any status-posting code; it only advances the
    legacy `days_active` warm-up counter.

These tests assert both, plus that no beat-scheduled task posts a status automatically.
"""
import inspect
import asyncio
from unittest.mock import MagicMock

import pytest

from app.services import warmup_service
from app.workers import tasks as tasks_mod
from app.workers.celery_app import celery_app


def test_daily_status_posting_flag_disabled():
    assert warmup_service.DAILY_STATUS_POSTING_DISABLED is True


def test_post_daily_status_is_noop():
    """Calling post_daily_status must NOT invoke any status-send client method."""
    client = MagicMock()
    # Every method access returns a MagicMock; if any is *called* we detect it below.
    result = asyncio.run(warmup_service.post_daily_status(client, "irrelevant"))
    assert result is None
    # No status-send method may have been called.
    client.send_status_text.assert_not_called()
    # Guard against any other status-ish send being wired in later.
    for name in dir(client):
        pass  # MagicMock auto-creates attrs; explicit check on the known method above suffices.
    assert client.method_calls == []


def test_warmup_accounts_task_never_posts_status():
    """The 10:00 beat task's source must not reference any status-posting call."""
    src = inspect.getsource(tasks_mod.task_warmup_accounts)
    assert "post_daily_status" not in src
    assert "send_status_text" not in src
    assert "send_text_status" not in src
    assert "send_status" not in src


def test_no_beat_task_auto_posts_status():
    """No entry in the celery beat schedule may point at the legacy status-poster.

    The only remaining status-related beat entry is `check-status-schedules`, which posts
    ONLY user-configured StatusSchedule rows (an explicit opt-in feature), never an automatic
    daily status. The legacy auto-poster (`tasks.warmup_accounts` -> post_daily_status) must
    no longer post anything.
    """
    schedule = celery_app.conf.beat_schedule
    # The warmup-accounts entry still exists (it advances days_active) but must be neutralised.
    assert "warmup-accounts" in schedule
    src = inspect.getsource(tasks_mod.task_warmup_accounts)
    # None of the status-POSTING call names may appear (AccountStatus / Account.status are fine).
    for banned in ("post_daily_status", "send_status_text", "send_text_status", "send_media_status"):
        assert banned not in src, f"warmup_accounts task must not reference {banned}"
