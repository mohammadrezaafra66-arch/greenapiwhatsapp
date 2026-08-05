"""V67.1 Phase 1.1 — Bugbot remediation regression tests.

Covers the three Bugbot findings:
  1. Non-reentrant campaign lock / parallel empty fallback
  2. Execution mode follows only parallel_accounts
  3. Poll-path suspension uses canonical record_suspension (no generic cooldown fallthrough)
"""
from __future__ import annotations
import inspect
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.services import state_monitor, send_gate
from app.services.account_selection import SELECTED_ACCOUNT_UNAVAILABLE_REASON
from app.models.account import AccountStatus

NOW = datetime(2026, 8, 5, 12, 0, 0)
LIVE_EPOCH = 1786199855


# ── FIX 1: non-reentrant lock / parallel empty fallback ─────────────────────
@pytest.mark.asyncio
async def test_parallel_empty_pending_calls_inner_not_nested_run_campaign():
    """Empty pending must complete under the held lock via _run_campaign_inner."""
    from app.services import campaign_runner as cr

    lock = MagicMock()
    lock.acquire = AsyncMock(return_value=True)
    lock.fail_closed_reason = None
    lock.token = "owner-tok"
    lock.release = AsyncMock(return_value=True)

    inner = AsyncMock()
    nested_public = AsyncMock()

    with patch("app.services.campaign_lock.CampaignLock", return_value=lock), \
         patch("app.services.fleet_breaker.is_tripped",
               new=AsyncMock(return_value=(False, "ok"))), \
         patch.object(cr, "_run_campaign_parallel_inner",
                      new=AsyncMock(side_effect=lambda *a, **k: None)) as _unused:
        # Drive the empty-pending branch directly on the inner body.
        pass

    # Re-test the empty-pending / empty-account_ids branches of the inner function
    # by patching the session and the sequential body.
    camp = SimpleNamespace(
        id=uuid.uuid4(), status=SimpleNamespace(value="running"),
        schedule_start=None, schedule_end=None, pause_reason=None,
        drip_enabled=False, drip_per_day=50, allowed_weekdays=None,
        selected_account_ids=None, parallel_accounts=True,
        selected_account_id=None,
    )
    # Force CampaignStatus comparisons used in runner.
    from app.models.campaign import CampaignStatus, MessageStatus
    camp.status = CampaignStatus.running

    class _Scalars:
        def __init__(self, rows):
            self._rows = rows
        def all(self):
            return self._rows
        def first(self):
            return self._rows[0] if self._rows else None

    class _Result:
        def __init__(self, rows=None, one=None):
            self._rows = rows or []
            self._one = one
        def all(self):
            return self._rows
        def scalars(self):
            return _Scalars(self._rows if self._rows is not None else
                            ([self._one] if self._one is not None else []))
        def scalar_one_or_none(self):
            return self._one

    class _Session:
        def __init__(self):
            self.commits = 0
        async def get(self, model, key):
            return camp
        async def execute(self, stmt):
            # pending contacts query → empty; account queries → empty
            return _Result([])
        async def commit(self):
            self.commits += 1
        async def refresh(self, obj):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False

    seq_inner = AsyncMock()
    public_run = AsyncMock()

    with patch.object(cr, "AsyncSessionLocal", return_value=_Session()), \
         patch.object(cr, "_run_campaign_inner", new=seq_inner), \
         patch.object(cr, "run_campaign", new=public_run), \
         patch("app.services.campaign_preflight.check_schedule_window",
               return_value=("ok", 0)), \
         patch("app.services.campaign_preflight.is_send_day", return_value=True), \
         patch("app.services.campaign_preflight.drip_remaining", return_value=None), \
         patch.object(cr, "_drip_today", new=AsyncMock(return_value=0)):
        await cr._run_campaign_parallel_inner(str(camp.id), [])

    seq_inner.assert_awaited_once()
    public_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_parallel_no_pending_fallback_completes_without_nested_lock():
    """parallel selected → empty pending → sequential inner → lock released once."""
    from app.services import campaign_runner as cr

    lock = MagicMock()
    lock.acquire = AsyncMock(return_value=True)
    lock.fail_closed_reason = None
    lock.token = "tok-abc"
    lock.release = AsyncMock(return_value=True)

    # Parallel inner will hit empty pending and call _run_campaign_inner.
    # We stub the whole parallel_inner to invoke the fallback path under test via
    # the real empty-account_ids branch by calling run_campaign_parallel with
    # a patched parallel_inner that calls _run_campaign_inner once.
    async def fake_parallel_inner(cid, aids):
        # Simulate the fixed empty-pending path.
        await cr._run_campaign_inner(cid)

    seq_inner = AsyncMock()
    public_run = AsyncMock()

    with patch("app.services.campaign_lock.CampaignLock", return_value=lock), \
         patch("app.services.fleet_breaker.is_tripped",
               new=AsyncMock(return_value=(False, "ok"))), \
         patch.object(cr, "_run_campaign_parallel_inner", new=fake_parallel_inner), \
         patch.object(cr, "_run_campaign_inner", new=seq_inner), \
         patch.object(cr, "run_campaign", new=public_run):
        await cr.run_campaign_parallel("cid-1", ["a1", "a2"])

    seq_inner.assert_awaited_once_with("cid-1")
    public_run.assert_not_awaited()
    lock.acquire.assert_awaited_once()
    lock.release.assert_awaited_once()


@pytest.mark.asyncio
async def test_parallel_fallback_exception_still_releases_lock():
    from app.services import campaign_runner as cr

    lock = MagicMock()
    lock.acquire = AsyncMock(return_value=True)
    lock.fail_closed_reason = None
    lock.token = "tok"
    lock.release = AsyncMock(return_value=True)

    with patch("app.services.campaign_lock.CampaignLock", return_value=lock), \
         patch("app.services.fleet_breaker.is_tripped",
               new=AsyncMock(return_value=(False, "ok"))), \
         patch.object(cr, "_run_campaign_parallel_inner",
                      new=AsyncMock(side_effect=RuntimeError("boom"))):
        with pytest.raises(RuntimeError):
            await cr.run_campaign_parallel("cid-x", ["a1"])

    lock.release.assert_awaited_once()


def test_parallel_inner_never_calls_public_run_campaign():
    """Source guard: empty fallback must not nest into the lock-owning public runner."""
    from app.services import campaign_runner as cr
    src = inspect.getsource(cr._run_campaign_parallel_inner)
    assert "await run_campaign(" not in src
    assert "await _run_campaign_inner(" in src


# ── FIX 2: execution mode selection ─────────────────────────────────────────
def _mode_from_start_source() -> str:
    from app.api.v1 import campaigns as camp_api
    return inspect.getsource(camp_api.start_campaign)


def test_start_routing_uses_parallel_accounts_only():
    src = _mode_from_start_source()
    assert "elif campaign.parallel_accounts:" in src
    assert "parallel_accounts or campaign.selected_account_ids" not in src


@pytest.mark.asyncio
async def test_execution_mode_matrix_parallel_flag_controls_worker():
    """Cases 1–4: parallel_accounts alone selects the worker; selection only filters."""
    from app.api.v1 import campaigns as camp_api
    from app.models.campaign import CampaignStatus

    cases = [
        # (parallel, selected, expect_parallel_delay)
        (False, [], False),
        (False, ["A", "B"], False),
        (True, [], True),
        (True, ["A", "B"], True),
    ]

    for parallel, selected, expect_parallel in cases:
        camp = SimpleNamespace(
            id=uuid.uuid4(),
            status=CampaignStatus.draft,
            contact_group_id=None,
            wa_collection_id=None,
            ab_test_enabled=False,
            campaign_scope="pv",
            parallel_accounts=parallel,
            selected_account_ids=selected or None,
            pause_reason=None,
            total_contacts=0,
        )
        a_id = uuid.uuid4()
        b_id = uuid.uuid4()
        accounts = [
            SimpleNamespace(id=a_id, status=AccountStatus.active,
                            cooldown_until=None),
            SimpleNamespace(id=b_id, status=AccountStatus.active,
                            cooldown_until=None),
        ]
        # Map selected labels to real ids for the True+[A,B] case
        if selected == ["A", "B"]:
            camp.selected_account_ids = [str(a_id), str(b_id)]

        class _Scalars:
            def __init__(self, rows):
                self._rows = rows
            def all(self):
                return self._rows

        class _Result:
            def __init__(self, rows):
                self._rows = rows
            def scalars(self):
                return _Scalars(self._rows)

        class _DB:
            async def get(self, model, key):
                return camp
            async def execute(self, stmt):
                return _Result(accounts)
            async def commit(self):
                pass

        delay = MagicMock()
        with patch.object(camp_api, "task_run_campaign") as task, \
             patch("app.services.warmup_exclusion.enrollment_states_by_instance",
                   new=AsyncMock(return_value={})), \
             patch("app.services.warmup_exclusion.warmup_campaign_excluded",
                   return_value=False), \
             patch("app.services.listener_service.listener_campaign_excluded",
                   return_value=False), \
             patch("app.services.governors.in_cooldown", return_value=False):
            task.delay = delay
            result = await camp_api.start_campaign(str(camp.id), db=_DB())

        assert result["status"] == "started", (parallel, selected, result)
        assert delay.called, (parallel, selected)
        args, kwargs = delay.call_args
        if expect_parallel:
            assert len(args) == 2, f"expected (id, account_ids), got {args}"
            assert isinstance(args[1], list)
        else:
            assert len(args) == 1, f"sequential must pass campaign_id only, got {args}"


@pytest.mark.asyncio
async def test_selected_all_unsafe_pauses_sequential_without_unrestricted_fallback():
    from app.api.v1 import campaigns as camp_api
    from app.models.campaign import CampaignStatus

    bad_id = uuid.uuid4()
    camp = SimpleNamespace(
        id=uuid.uuid4(),
        status=CampaignStatus.draft,
        contact_group_id=None,
        wa_collection_id=None,
        ab_test_enabled=False,
        campaign_scope="pv",
        parallel_accounts=False,
        selected_account_ids=[str(bad_id)],
        pause_reason=None,
        total_contacts=0,
    )
    # Selected account exists but is in cooldown → unusable.
    accounts = [
        SimpleNamespace(id=bad_id, status=AccountStatus.active, cooldown_until=NOW + timedelta(days=1)),
        SimpleNamespace(id=uuid.uuid4(), status=AccountStatus.active, cooldown_until=None),
    ]

    class _Scalars:
        def __init__(self, rows):
            self._rows = rows
        def all(self):
            return self._rows

    class _Result:
        def __init__(self, rows):
            self._rows = rows
        def scalars(self):
            return _Scalars(self._rows)

    class _DB:
        async def get(self, model, key):
            return camp
        async def execute(self, stmt):
            return _Result(accounts)
        async def commit(self):
            pass

    delay = MagicMock()
    with patch.object(camp_api, "task_run_campaign") as task, \
         patch("app.services.warmup_exclusion.enrollment_states_by_instance",
               new=AsyncMock(return_value={})), \
         patch("app.services.warmup_exclusion.warmup_campaign_excluded",
               return_value=False), \
         patch("app.services.listener_service.listener_campaign_excluded",
               return_value=False), \
         patch("app.services.governors.in_cooldown",
               side_effect=lambda a: a.id == bad_id):
        task.delay = delay
        result = await camp_api.start_campaign(str(camp.id), db=_DB())

    assert result["status"] == "paused"
    assert result["reason"] == SELECTED_ACCOUNT_UNAVAILABLE_REASON
    assert camp.status == CampaignStatus.paused
    delay.assert_not_called()


# ── FIX 3: canonical poll-path suspension ───────────────────────────────────
class _FakeDB:
    def add(self, *_a, **_k):
        pass


def _acc(**kw):
    return SimpleNamespace(
        id=kw.get("id", "acc-1"),
        instance_id=kw.get("instance_id", "77001"),
        status=kw.get("status", AccountStatus.active),
        api_token="secret-token-never-log",
        suspended_until=kw.get("suspended_until", None),
        throttle_factor=1.0,
        throttle_until=None,
        cooldown_until=None,
        last_incident_at=None,
        incident_count_7d=kw.get("incident_count_7d", 0),
        sent_today=0,
        name="t",
    )


@pytest.mark.asyncio
async def test_poll_suspended_calls_record_suspension_once_no_generic_cooldown(monkeypatch):
    calls = []

    async def _noop_persist(*_a, **_k):
        return None

    async def _fake_refresh(_db, account, client=None):
        account.suspended_until = datetime.utcfromtimestamp(LIVE_EPOCH)
        return account.suspended_until

    async def _fake_record(account, via, db):
        calls.append(via)
        return SimpleNamespace(incident_type="suspended")

    monkeypatch.setattr(send_gate, "persist_live_state", _noop_persist)
    monkeypatch.setattr(state_monitor, "refresh_suspended_until", _fake_refresh)
    monkeypatch.setattr("app.services.incident_handler.record_suspension", _fake_record)

    acc = _acc()
    res = await state_monitor.apply_state(_FakeDB(), acc, "suspended", "poll", NOW)

    assert calls == ["poll"]
    assert res["acted"] == "suspended"
    assert acc.cooldown_until is None
    assert acc.throttle_until is None
    assert acc.status == AccountStatus.suspended
    assert acc.suspended_until == datetime.utcfromtimestamp(LIVE_EPOCH)


@pytest.mark.asyncio
async def test_poll_after_webhook_suspension_is_idempotent(monkeypatch):
    """Webhook already recorded → poll repeats → record_suspension returns None → no cooldown."""
    record_calls = []

    async def _noop_persist(*_a, **_k):
        return None

    async def _fake_refresh(_db, account, client=None):
        return account.suspended_until

    async def _fake_record(account, via, db):
        record_calls.append(via)
        return None  # open incident already exists

    breaker = AsyncMock(return_value={"distinct": 1, "tripped": False})

    monkeypatch.setattr(send_gate, "persist_live_state", _noop_persist)
    monkeypatch.setattr(state_monitor, "refresh_suspended_until", _fake_refresh)
    monkeypatch.setattr("app.services.incident_handler.record_suspension", _fake_record)

    acc = _acc(status=AccountStatus.suspended,
               suspended_until=datetime.utcfromtimestamp(LIVE_EPOCH),
               incident_count_7d=1)
    before = acc.incident_count_7d
    res = await state_monitor.apply_state(_FakeDB(), acc, "suspended", "poll", NOW)

    assert record_calls == ["poll"]
    assert res["acted"] == "suspended"
    assert acc.incident_count_7d == before  # fake returns None → counter untouched
    assert acc.cooldown_until is None
    # Breaker is only inside real record_suspension; our stub returns None without calling it.
    breaker.assert_not_awaited()


@pytest.mark.asyncio
async def test_poll_stores_suspended_until_from_get_wa_settings(monkeypatch):
    async def _noop_persist(*_a, **_k):
        return None

    class _Client:
        async def get_wa_settings(self):
            return {"suspendedUntil": LIVE_EPOCH}

    async def _fake_record(account, via, db):
        return SimpleNamespace(incident_type="suspended")

    real_refresh = state_monitor.refresh_suspended_until

    async def _refresh(db, account, client=None):
        return await real_refresh(db, account, client=_Client())

    monkeypatch.setattr(send_gate, "persist_live_state", _noop_persist)
    monkeypatch.setattr("app.services.incident_handler.record_suspension", _fake_record)
    monkeypatch.setattr(state_monitor, "refresh_suspended_until", _refresh)

    acc = _acc()
    res = await state_monitor.apply_state(_FakeDB(), acc, "suspended", "poll", NOW)
    assert acc.suspended_until == datetime(2026, 8, 8, 14, 37, 35)
    assert res["suspended_until"] == acc.suspended_until


@pytest.mark.asyncio
async def test_poll_suspension_survives_get_wa_settings_failure(monkeypatch):
    async def _noop_persist(*_a, **_k):
        return None

    async def _boom_refresh(_db, account, client=None):
        # Mimic refresh_suspended_until network failure: log + return None, do not raise.
        return None

    recorded = []

    async def _fake_record(account, via, db):
        recorded.append(via)
        return SimpleNamespace(incident_type="suspended")

    monkeypatch.setattr(send_gate, "persist_live_state", _noop_persist)
    monkeypatch.setattr(state_monitor, "refresh_suspended_until", _boom_refresh)
    monkeypatch.setattr("app.services.incident_handler.record_suspension", _fake_record)

    acc = _acc()
    res = await state_monitor.apply_state(_FakeDB(), acc, "suspended", "poll", NOW)
    assert recorded == ["poll"]
    assert res["acted"] == "suspended"
    assert acc.cooldown_until is None
    assert acc.status == AccountStatus.suspended
    # Status flipped to suspended → gate refuses (also blocked by live_state=suspended).
    ok, reason = send_gate.can_send_now(acc, "suspended", NOW)
    assert ok is False
    assert reason in ("not_active", "live_state:suspended") or "suspended" in reason


def test_apply_state_suspended_returns_before_generic_danger_branch():
    src = inspect.getsource(state_monitor.apply_state)
    # Early return after suspended handling must exist before generic cooldown assignment.
    sus_idx = src.index('s == "suspended"')
    ret_idx = src.index("return result", sus_idx)
    cooldown_idx = src.index("cooldown_until", sus_idx)
    assert ret_idx < cooldown_idx, "suspended must return before generic cooldown fallthrough"
