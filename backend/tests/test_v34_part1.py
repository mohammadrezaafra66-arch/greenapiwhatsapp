"""V34 — decouple «همکاری تیمی» (Team Collaboration) reminder/no_response from the mesh PAUSE state.

Team Collaboration is a separate track from the mesh warm-up. Before V34, run_helper_tick only
processed a cold account whose MESH enrollment was «being warmed» (state not in
GRADUATED/PAUSED/BLOCKED_RESET). So when the mesh chain-ban breaker paused the WHOLE mesh (because
OTHER numbers carded), a genuinely-healthy TC cold stopped getting reminders and never reached
no_response. V34 adds `tc_eligible_cold_instances`: a team-enrolled cold progresses on its OWN V27
health gate, independent of mesh PAUSE — but the gate is NOT weakened (a live yellowCard/blocked,
cooldown, throttle, or non-active status still excludes it).
"""
import uuid
import random
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.services import warmup_helper_engine as he
from app.services import warmup_helper_service as hs
from app.services import send_gate, peer_pacer
from app.models.account import Account, AccountStatus
from app.models.warmup_helpers import WarmupHelper, WarmupHelperTask, WarmupHelperConfig
from app.services.warmup_state import WarmupState

NOW = datetime(2026, 5, 4, 11, 0)
WINDOW = hs.REMINDER_AFTER_MINUTES


@pytest.fixture(autouse=True)
def _reset():
    send_gate.clear_live_cache()
    peer_pacer.reset()
    yield
    send_gate.clear_live_cache()
    peer_pacer.reset()


def _cold(iid, *, active=True, cooldown_until=None, throttle_until=None, throttle_factor=1.0,
          warm=False, phone=None):
    a = Account(name=iid, instance_id=iid, api_token="t")
    a.id = uuid.uuid4()
    a.status = AccountStatus.active if active else AccountStatus.disconnected
    a.cooldown_until = cooldown_until
    a.throttle_until = throttle_until
    a.throttle_factor = throttle_factor
    a.is_warm_peer = warm
    a.phone = phone
    return a


# ── unit: tc_eligible_cold_instances ─────────────────────────────────────────
class _TEDB:
    """Serves only the tc_eligible team-enrollment column query."""
    def __init__(self, enrolled):
        self.enrolled = list(enrolled)

    async def execute(self, q):
        enrolled = self.enrolled

        class _R:
            def all(_s):
                return [(c,) for c in enrolled]
        return _R()


@pytest.mark.asyncio
async def test_healthy_team_cold_is_eligible():
    out = await he.tc_eligible_cold_instances(_TEDB(["C1"]), {"C1": _cold("C1")})
    assert out == ["C1"]


@pytest.mark.asyncio
async def test_eligibility_ignores_mesh_state_entirely():
    """tc_eligible takes NO mesh-state input — a healthy team-enrolled cold is eligible regardless of
    whatever the mesh track's state (PAUSED, etc.) happens to be. The decoupling is structural."""
    out = await he.tc_eligible_cold_instances(_TEDB(["C1", "C2"]),
                                              {"C1": _cold("C1"), "C2": _cold("C2")})
    assert set(out) == {"C1", "C2"}


@pytest.mark.asyncio
async def test_live_yellowcard_cold_excluded():
    send_gate.update_live_state("C1", "yellowcard")           # fresh live danger state
    out = await he.tc_eligible_cold_instances(_TEDB(["C1"]), {"C1": _cold("C1")})
    assert out == []


@pytest.mark.asyncio
async def test_live_blocked_cold_excluded():
    send_gate.update_live_state("C1", "blocked")
    out = await he.tc_eligible_cold_instances(_TEDB(["C1"]), {"C1": _cold("C1")})
    assert out == []


@pytest.mark.asyncio
async def test_cooldown_cold_excluded():
    c = _cold("C1", cooldown_until=datetime.utcnow() + timedelta(hours=2))
    out = await he.tc_eligible_cold_instances(_TEDB(["C1"]), {"C1": c})
    assert out == []


@pytest.mark.asyncio
async def test_non_active_status_cold_excluded():
    out = await he.tc_eligible_cold_instances(_TEDB(["C1"]), {"C1": _cold("C1", active=False)})
    assert out == []


@pytest.mark.asyncio
async def test_not_team_enrolled_excluded():
    out = await he.tc_eligible_cold_instances(_TEDB([]), {"C1": _cold("C1")})
    assert out == []


@pytest.mark.asyncio
async def test_missing_account_skipped():
    out = await he.tc_eligible_cold_instances(_TEDB(["C1"]), {})   # no loaded Account → can't gate
    assert out == []


# ── integration: run_helper_tick processes a mesh-PAUSED-but-healthy TC cold ─
class _TickDB:
    def __init__(self, *, helpers, tasks, accounts, mesh_states, team_enrolled, config):
        self.helpers, self.tasks, self.accounts = list(helpers), list(tasks), list(accounts)
        self.mesh_states = list(mesh_states)       # (iid, state, enabled)
        self.team_enrolled = list(team_enrolled)   # enabled cold ids
        self.config = config
        self.added, self.commits = [], 0

    def _sql(self, q):
        try:
            return str(q.compile(compile_kwargs={"literal_binds": True})).lower()
        except Exception:
            return str(q).lower()

    async def execute(self, q):
        sql = self._sql(q)

        class _R:
            def __init__(_s, scalars=None, rows=None):
                _s._s = list(scalars) if scalars is not None else []
                _s._rows = list(rows) if rows is not None else []

            def scalars(_s):
                class _S:
                    def all(__s):
                        return list(_s._s)
                return _S()

            def all(_s):
                return list(_s._rows)

            def scalar_one_or_none(_s):
                return _s._s[0] if _s._s else None
        if "warmup_helper_config" in sql:
            return _R(scalars=[self.config] if self.config else [])
        if "warmup_team_enrollment" in sql:
            return _R(rows=[(c,) for c in self.team_enrolled])
        if "warmup_helper_thread" in sql:
            return _R(scalars=[])
        if "outreach_brief" in sql or "warmup_helper_log" in sql:
            return _R(scalars=[], rows=[])
        if "warmup_helper_task" in sql:
            if "warmup_helper_task.id" in sql:
                rows = list(self.tasks)
                if "reminder_count >=" in sql:                 # expire query
                    return _R(scalars=[])                      # nothing exhausted in these tests
                if "status in" in sql or "status =" in sql:
                    rows = [t for t in rows if f"'{t.status}'" in sql]
                if "cold_instance_id =" in sql:
                    rows = [t for t in rows if t.cold_instance_id.lower() in sql]
                return _R(scalars=rows)
            return _R(rows=[(t.helper_id, t.cold_instance_id) for t in self.tasks])
        if "warmup_helper" in sql:
            return _R(scalars=list(self.helpers))
        if "warmup_enrollment" in sql:
            return _R(rows=list(self.mesh_states))
        if "accounts" in sql:
            match = [a for a in self.accounts if a.instance_id.lower() in sql]
            if match and "instance_id =" in sql:
                return _R(scalars=match)
            return _R(scalars=[a for a in self.accounts if a.status == AccountStatus.active])
        return _R()

    def add(self, o):
        self.added.append(o)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def refresh(self, o):
        pass

    async def get(self, model, pk):
        for h in self.helpers:
            if getattr(h, "id", None) == pk:
                return h
        return None


def _reminded_task(helper_id, cold, count=1):
    t = WarmupHelperTask(helper_id=helper_id, cold_instance_id=cold, status=hs.STATUS_REMINDED)
    t.id = uuid.uuid4()
    t.created_at = NOW - timedelta(hours=3)
    t.asked_at = NOW - timedelta(minutes=3 * WINDOW)
    t.reminded_at = NOW - timedelta(minutes=WINDOW + 30)   # window elapsed → reminder #2 due
    t.reminder_count = count
    return t


def _scenario(cold_live_state=None):
    sender = _cold("P1", warm=True, phone="989000000000")
    cold = _cold("C1", phone="989048249532")               # healthy account (no cooldown/throttle)
    helper = WarmupHelper(name="رضا محمدی", phone="989111111111", is_active=True, sender_instance_id="P1")
    helper.id = uuid.uuid4()
    task = _reminded_task(helper.id, "C1", count=1)
    config = WarmupHelperConfig(is_enabled=True, next_ask_at=None)
    db = _TickDB(helpers=[helper], tasks=[task], accounts=[sender, cold],
                 mesh_states=[("C1", WarmupState.PAUSED.value, True)],   # MESH PAUSED
                 team_enrolled=["C1"], config=config)
    if cold_live_state:
        send_gate.update_live_state("C1", cold_live_state)
    return db, task


def _factory(store):
    def factory(iid, tok):
        c = MagicMock()
        c.send_typing_ms = AsyncMock(return_value=True)

        async def _s(p, t):
            store["sent"] = {"from": iid, "to": p, "text": t}
            return "MID"
        c.send_message = AsyncMock(side_effect=_s)
        return c
    return factory


@pytest.mark.asyncio
async def test_mesh_paused_but_healthy_cold_still_gets_reminder(monkeypatch):
    """The regression fix: cold is MESH-PAUSED (excluded from `cold_instances_being_warmed`) but
    team-enrolled and healthy → run_helper_tick still sends its 2nd reminder."""
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    db, task = _scenario(cold_live_state=None)              # healthy: no blocking live state
    store = {}
    res = await he.run_helper_tick(db, now=NOW, client_factory=_factory(store), rng=random.Random(1))
    assert res["acted"] == 1 and res["kind"] == "remind"
    assert task.status == hs.STATUS_REMINDED and task.reminder_count == 2   # reminder #2 fired
    assert store["sent"]["to"] == "989111111111"


@pytest.mark.asyncio
async def test_unhealthy_cold_still_excluded_even_if_team_enrolled(monkeypatch):
    """The guardrail: a team-enrolled cold that is genuinely unhealthy (live yellowCard) is still
    excluded by the V27 gate → run_helper_tick does NOT process it (no reminder)."""
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    db, task = _scenario(cold_live_state="yellowcard")     # genuinely unhealthy cold
    store = {}
    res = await he.run_helper_tick(db, now=NOW, client_factory=_factory(store), rng=random.Random(1))
    assert res["acted"] == 0                                # nothing due (cold gated out)
    assert task.status == hs.STATUS_REMINDED and task.reminder_count == 1   # unchanged
    assert store == {}                                      # no send
