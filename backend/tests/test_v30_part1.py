"""V30 PART 1 — «همکاری تیمی» frontend enablement: the new manual thread-resume endpoint.

The frontend Alerts page lets an admin decide a safety-paused thread is a false positive and
RESUME it. This proves the endpoint: it acknowledges the alert AND flips a paused thread back to
active, is a no-op-resume (still acks) for an already-active thread, and 404s on a missing alert.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException

from app.api.v1 import warmup_helpers as api
from app.services import warmup_helper_thread as wt
from app.models.warmup_helpers import WarmupThreadAlert, WarmupHelperThread


def _db_with(alert, thread):
    db = AsyncMock()

    def _get(model, _id):
        if model is WarmupThreadAlert:
            return alert
        if model is WarmupHelperThread:
            return thread
        return None
    db.get = AsyncMock(side_effect=_get)
    return db


@pytest.mark.asyncio
async def test_resume_reactivates_paused_thread_and_acks():
    tid = uuid.uuid4()
    alert = SimpleNamespace(thread_id=tid, acknowledged=False)
    thread = SimpleNamespace(status=wt.STATUS_PAUSED)
    db = _db_with(alert, thread)

    r = await api.resume_thread_from_alert(str(uuid.uuid4()), db=db)

    assert alert.acknowledged is True
    assert thread.status == wt.STATUS_ACTIVE
    assert r["resumed"] is True
    assert r["acknowledged"] is True
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_resume_is_noop_but_acks_when_thread_already_active():
    tid = uuid.uuid4()
    alert = SimpleNamespace(thread_id=tid, acknowledged=False)
    thread = SimpleNamespace(status=wt.STATUS_ACTIVE)
    db = _db_with(alert, thread)

    r = await api.resume_thread_from_alert(str(uuid.uuid4()), db=db)

    assert alert.acknowledged is True          # still acknowledged
    assert thread.status == wt.STATUS_ACTIVE    # unchanged
    assert r["resumed"] is False


@pytest.mark.asyncio
async def test_resume_missing_alert_404():
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as ei:
        await api.resume_thread_from_alert(str(uuid.uuid4()), db=db)
    assert ei.value.status_code == 404
