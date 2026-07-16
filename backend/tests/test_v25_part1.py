"""V25 PART 1 — "human helpers" warm-up assist.

Proves the anti-spam + anti-ban guarantees:
  • hard 25-active cap (26th rejected with a Persian error),
  • the toggle-ON flow creates tasks but sends SLOWLY (one ask/reminder per tick, waking
    hours only, jittered rate gate — never a burst even with 25 helpers × many cold numbers),
  • the wa.me link is built from the cold number's real phone (resolved via getWaSettings
    when null),
  • an incoming message from a helper marks the task done + auto-sends a thank-you,
  • no success within 1h → exactly ONE reminder, never a second.
"""
import uuid
import random
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models.account import Account, AccountStatus
from app.models.warmup_helpers import WarmupHelper, WarmupHelperTask, WarmupHelperConfig
from app.services import warmup_helper_service as hs
from app.services import warmup_helper_engine as he
from app.services.warmup_state import WarmupState, DEFAULT_WARMUP_CONFIG


# in_active_hours treats a NAIVE datetime as Tehran-local, so these are Tehran wall-clock.
TEHRAN_11AM = datetime(2026, 5, 4, 11, 0)   # 11:00 Tehran — inside 09:00–21:00
TEHRAN_3AM = datetime(2026, 5, 4, 3, 0)     # 03:00 Tehran — outside waking hours


# ── pure: wa.me link + digit extraction ─────────────────────────────────────
def test_wa_me_digits_strips_everything_nonnumeric():
    assert hs.wa_me_digits("+98 904-824 9532") == "989048249532"
    assert hs.wa_me_digits("989048249532@c.us") == "989048249532"
    assert hs.wa_me_digits("۹۸۹۰۴۸۲۴۹۵۳۲") == "989048249532"   # Persian digits
    assert hs.wa_me_digits(None) == ""
    assert hs.wa_me_digits("") == ""


def test_wa_me_link_built_from_real_phone():
    assert hs.wa_me_link("+98 904 824 9532") == "https://wa.me/989048249532"
    assert hs.wa_me_link(None) is None       # no phone → caller must resolve first
    assert hs.wa_me_link("---") is None


# ── pure: Persian message builders (link + suggested text included) ──────────
def test_ask_message_contains_link_and_suggestion():
    msg = hs.build_ask_message("رضا", "https://wa.me/989048249532")
    assert "رضا" in msg
    assert "https://wa.me/989048249532" in msg
    assert hs.SUGGESTED_TEXT in msg


def test_ask_message_without_name_or_link_is_still_valid():
    msg = hs.build_ask_message(None, None)
    assert "سلام" in msg and hs.SUGGESTED_TEXT in msg
    assert "wa.me" not in msg


def test_reminder_and_thankyou_messages():
    rem = hs.build_reminder_message("مریم", "https://wa.me/98123")
    assert "مریم" in rem and "https://wa.me/98123" in rem
    assert hs.build_thankyou_message("علی") == "ممنون از لطفت علی 🙏"
    assert hs.build_thankyou_message(None) == "ممنون از لطفت 🙏"


# ── pure: slow-send rate gate ────────────────────────────────────────────────
def test_next_ask_at_within_jitter_bounds():
    rng = random.Random(0)
    for _ in range(200):
        nxt = hs.next_ask_at(TEHRAN_11AM, rng)
        gap = (nxt - TEHRAN_11AM).total_seconds()
        assert hs.HELPER_ASK_MIN_GAP_SECONDS <= gap <= hs.HELPER_ASK_MAX_GAP_SECONDS


def test_can_ask_now_requires_waking_hours():
    assert hs.can_ask_now(TEHRAN_11AM, None) is True
    assert hs.can_ask_now(TEHRAN_3AM, None) is False           # outside 09:00–21:00 → blocked


def test_can_ask_now_respects_rate_gate():
    gate = TEHRAN_11AM + timedelta(minutes=5)
    assert hs.can_ask_now(TEHRAN_11AM, gate) is False          # gate not elapsed
    assert hs.can_ask_now(gate, gate) is True                  # exactly at the gate
    assert hs.can_ask_now(gate + timedelta(seconds=1), gate) is True


def test_rate_never_exceeded_over_a_full_day_simulation():
    """Even with unlimited demand, the gate spaces sends >= MIN gap apart and only in hours —
    the core protection for the main account (25 helpers × many cold numbers can't burst)."""
    rng = random.Random(42)
    now = datetime(2026, 5, 4, 5, 30)     # 09:00 Tehran
    end = now + timedelta(hours=24)
    gate = None
    sent_times = []
    while now < end:
        if hs.can_ask_now(now, gate):
            sent_times.append(now)
            gate = hs.next_ask_at(now, rng)
        now += timedelta(seconds=60)      # a tick per minute (denser than the real 180s beat)
    # Every consecutive pair is at least the MIN gap apart.
    for a, b in zip(sent_times, sent_times[1:]):
        assert (b - a).total_seconds() >= hs.HELPER_ASK_MIN_GAP_SECONDS
    # Nothing was sent outside waking hours.
    assert all(hs.can_ask_now(t, None) for t in sent_times)
    # A whole day of 12 waking hours at >=3 min spacing can never exceed 12*60/3 = 240 asks.
    assert len(sent_times) <= 240


# ── pure: pick_main_sender never picks a cold number, prefers a warm peer ─────
def _acc(iid, *, warm=False, active=True):
    a = Account(name=f"acc-{iid}", instance_id=iid, api_token="t")
    a.id = uuid.uuid4()
    a.status = AccountStatus.active if active else AccountStatus.disconnected
    a.is_warm_peer = warm
    a.phone = f"9891222{iid[-4:]}"
    return a


def test_pick_main_sender_prefers_warm_peer():
    peer = _acc("P1", warm=True)
    cold = _acc("C1")
    enr = {"C1": (WarmupState.RECEIVING.value, True)}
    assert he.pick_main_sender([cold, peer], enr) is peer


def test_pick_main_sender_falls_back_to_graduated_then_other_never_cold():
    grad = _acc("G1")
    cold = _acc("C1")
    enr = {"G1": (WarmupState.GRADUATED.value, True), "C1": (WarmupState.RECEIVING.value, True)}
    # no warm peer → graduated wins, and the actively-warmed cold number is never chosen
    got = he.pick_main_sender([cold, grad], enr)
    assert got is grad
    # with neither peer nor graduated, an idle account is used — but never the warmed cold one
    other = _acc("O1")
    enr2 = {"C1": (WarmupState.RECEIVING.value, True)}
    got2 = he.pick_main_sender([cold, other], enr2)
    assert got2 is other
    # only a being-warmed cold number available → None (never send from a cold number)
    assert he.pick_main_sender([cold], enr2) is None


# ── pure: select_action — one action, reminder priority, one-reminder-max ─────
def _task(status, *, asked_min_ago=None, created_min_ago=0):
    t = WarmupHelperTask(helper_id=uuid.uuid4(), cold_instance_id="C1", status=status)
    t.id = uuid.uuid4()
    t.created_at = TEHRAN_11AM - timedelta(minutes=created_min_ago)
    t.asked_at = (TEHRAN_11AM - timedelta(minutes=asked_min_ago)) if asked_min_ago is not None else None
    return t


def test_select_action_picks_single_pending_when_no_reminder_due():
    p1, p2 = _task(hs.STATUS_PENDING, created_min_ago=10), _task(hs.STATUS_PENDING, created_min_ago=5)
    kind, task = he.select_action([p1, p2], [], TEHRAN_11AM)
    assert kind == "ask"
    assert task is p1          # oldest pending first — exactly ONE returned


def test_select_action_reminder_after_1h_takes_priority():
    pending = _task(hs.STATUS_PENDING)
    fresh_ask = _task(hs.STATUS_ASKED, asked_min_ago=30)     # < 1h → no reminder
    old_ask = _task(hs.STATUS_ASKED, asked_min_ago=90)       # > 1h → reminder due
    kind, task = he.select_action([pending], [fresh_ask, old_ask], TEHRAN_11AM)
    assert kind == "remind"
    assert task is old_ask


def test_select_action_no_reminder_before_1h():
    fresh_ask = _task(hs.STATUS_ASKED, asked_min_ago=59)
    # nothing pending and the ask is < 1h old → no action at all
    assert he.select_action([], [fresh_ask], TEHRAN_11AM) is None


def test_reminded_task_is_never_reminded_again():
    """A task already reminded is not status 'asked', so select_action never re-selects it —
    a helper is messaged at most ask + one reminder."""
    reminded = _task(hs.STATUS_REMINDED, asked_min_ago=200)
    reminded.reminded_at = TEHRAN_11AM - timedelta(hours=2)
    # only 'asked' tasks are eligible for a reminder; a reminded task is excluded upstream
    kind = he.select_action([], [], TEHRAN_11AM)
    assert kind is None
    # even if erroneously passed in, status != 'asked' so it is ignored
    assert he.select_action([], [reminded], TEHRAN_11AM) is None


# ── DB fake (routes by compiled SQL) for CRUD + engine integration ───────────
class FakeScalars:
    def __init__(self, items): self._items = list(items)
    def all(self): return list(self._items)


class FakeResult:
    def __init__(self, scalars=None, rows=None, scalar=None):
        self._scalars = list(scalars) if scalars is not None else []
        self._rows = list(rows) if rows is not None else []
        self._scalar = scalar
    def scalars(self): return FakeScalars(self._scalars)
    def all(self): return list(self._rows)
    def scalar(self): return self._scalar
    def scalar_one_or_none(self): return self._scalars[0] if self._scalars else None


class FakeDB:
    """Routes queries by their compiled SQL to in-memory lists. Enough for the helper
    service/engine, whose query shapes are distinct per table."""
    def __init__(self, helpers=None, tasks=None, accounts=None, enrollments=None, config=None):
        self.helpers = list(helpers or [])
        self.tasks = list(tasks or [])
        self.accounts = list(accounts or [])
        self.enrollments = list(enrollments or [])   # list of (instance_id, state, is_enabled)
        self.config = config
        self.added = []
        self.commits = 0

    def _sql(self, q):
        try:
            return str(q.compile(compile_kwargs={"literal_binds": True})).lower()
        except Exception:
            return str(q).lower()

    async def execute(self, q):
        sql = self._sql(q)
        if "count(" in sql:
            return FakeResult(scalar=sum(1 for h in self.helpers if h.is_active))
        if "warmup_helper_config" in sql:
            return FakeResult(scalars=[self.config] if self.config else [])
        if "warmup_helper_task" in sql:
            # the (helper_id, cold_instance_id) pair select used by ensure_helper_tasks
            if "warmup_helper_task.id" not in sql:
                return FakeResult(rows=[(t.helper_id, t.cold_instance_id) for t in self.tasks])
            rows = list(self.tasks)
            # status filter (crude): keep only statuses named in the SQL when a status clause exists
            if "status" in sql:
                rows = [t for t in rows if t.status in sql]
            # handle_helper_incoming filters by a specific cold_instance_id present in the SQL
            if "cold_instance_id =" in sql:
                rows = [t for t in rows if t.cold_instance_id.lower() in sql]
            return FakeResult(scalars=rows)
        if "warmup_helper" in sql:              # WarmupHelper entity/list
            rows = self.helpers
            # handle_helper_incoming filters by phone literal present in the SQL
            phones = [h for h in self.helpers if h.phone in sql]
            if phones and "phone =" in sql:
                rows = phones
            return FakeResult(scalars=rows)
        if "warmup_enrollment" in sql:
            return FakeResult(rows=list(self.enrollments))
        if "from accounts" in sql or " accounts " in sql or "accounts." in sql:
            # a single-instance lookup (resolve cold phone) → the matching account
            match = [a for a in self.accounts if a.instance_id.lower() in sql]
            if match and "instance_id =" in sql:
                return FakeResult(scalars=match)
            active = [a for a in self.accounts if a.status == AccountStatus.active]
            return FakeResult(scalars=active)
        return FakeResult()

    def add(self, o): self.added.append(o)
    async def flush(self): pass
    async def commit(self): self.commits += 1
    async def refresh(self, o): pass
    async def get(self, model, pk):
        for h in self.helpers:
            if getattr(h, "id", None) == pk:
                return h
        return None
    async def delete(self, o):
        if o in self.helpers:
            self.helpers.remove(o)


# ── 25-cap enforced (26th rejected) ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_helper_cap_rejects_26th():
    helpers = [WarmupHelper(name=f"h{i}", phone=f"9890000{i:04d}", is_active=True) for i in range(25)]
    for h in helpers:
        h.id = uuid.uuid4()
    db = FakeDB(helpers=helpers)
    with pytest.raises(hs.HelperCapError):
        await db_add_helper(db, "over", "989099999999")
    # a 26th INACTIVE helper is fine (doesn't count toward the active cap)
    inactive = await hs.add_helper(db, "backup", "989011112222", is_active=False)
    assert inactive.is_active is False


async def db_add_helper(db, name, phone):
    return await hs.add_helper(db, name, phone)


@pytest.mark.asyncio
async def test_helper_cap_allows_25():
    helpers = [WarmupHelper(name=f"h{i}", phone=f"9890000{i:04d}", is_active=True) for i in range(24)]
    for h in helpers:
        h.id = uuid.uuid4()
    db = FakeDB(helpers=helpers)
    h25 = await hs.add_helper(db, "number25", "989025252525")
    assert h25.name == "number25" and h25.phone == "989025252525"
    assert db.commits >= 1


# ── toggle ON: creates tasks + sends ONE ask slowly (in hours), re-arms gate ──
@pytest.mark.asyncio
async def test_toggle_on_sends_single_ask_and_arms_gate(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    helper = WarmupHelper(name="رضا", phone="989111111111", is_active=True)
    helper.id = uuid.uuid4()
    cold = _acc("C1"); cold.phone = "989048249532"
    peer = _acc("P1", warm=True)
    pending = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C1", status=hs.STATUS_PENDING)
    pending.id = uuid.uuid4(); pending.created_at = TEHRAN_11AM
    config = WarmupHelperConfig(is_enabled=True, next_ask_at=None)
    db = FakeDB(helpers=[helper], tasks=[pending], accounts=[cold, peer],
                enrollments=[("C1", WarmupState.RECEIVING.value, True)], config=config)

    sent = {}
    def factory(iid, tok):
        c = MagicMock()
        c.send_typing_ms = AsyncMock(return_value=True)
        async def _send(phone, text):
            sent["phone"] = phone; sent["text"] = text; return "MID1"
        c.send_message = AsyncMock(side_effect=_send)
        return c

    res = await he.run_helper_tick(db, now=TEHRAN_11AM, client_factory=factory, rng=random.Random(1))
    assert res["enabled"] and res["acted"] == 1 and res["kind"] == "ask"
    assert res["sent"] is True
    # the ask went to the HELPER's phone, from the warm peer, and carries the wa.me link
    assert sent["phone"] == "989111111111"
    assert "https://wa.me/989048249532" in sent["text"]
    assert hs.SUGGESTED_TEXT in sent["text"]
    assert pending.status == hs.STATUS_ASKED and pending.asked_at == TEHRAN_11AM
    # the rate gate was re-armed to a jittered future time (slow sends)
    gap = (config.next_ask_at - TEHRAN_11AM).total_seconds()
    assert hs.HELPER_ASK_MIN_GAP_SECONDS <= gap <= hs.HELPER_ASK_MAX_GAP_SECONDS


@pytest.mark.asyncio
async def test_disabled_toggle_is_noop():
    config = WarmupHelperConfig(is_enabled=False)
    db = FakeDB(config=config)
    res = await he.run_helper_tick(db, now=TEHRAN_11AM, client_factory=lambda *a: MagicMock())
    assert res == {"enabled": False, "acted": 0}


@pytest.mark.asyncio
async def test_outside_waking_hours_creates_tasks_but_sends_nothing():
    helper = WarmupHelper(name="رضا", phone="989111111111", is_active=True)
    helper.id = uuid.uuid4()
    config = WarmupHelperConfig(is_enabled=True, next_ask_at=None)
    db = FakeDB(helpers=[helper], tasks=[], accounts=[_acc("C1")],
                enrollments=[("C1", WarmupState.RECEIVING.value, True)], config=config)
    res = await he.run_helper_tick(db, now=TEHRAN_3AM, client_factory=lambda *a: MagicMock())
    assert res["enabled"] and res["acted"] == 0 and res["throttled"] is True
    assert res["in_hours"] is False
    # a pending task WAS created (spread), but no send happened outside hours
    assert any(isinstance(o, WarmupHelperTask) for o in db.added)


@pytest.mark.asyncio
async def test_gate_not_elapsed_blocks_second_send():
    helper = WarmupHelper(name="رضا", phone="989111111111", is_active=True)
    helper.id = uuid.uuid4()
    future_gate = TEHRAN_11AM + timedelta(minutes=5)
    config = WarmupHelperConfig(is_enabled=True, next_ask_at=future_gate)
    pending = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C1", status=hs.STATUS_PENDING)
    pending.id = uuid.uuid4(); pending.created_at = TEHRAN_11AM
    db = FakeDB(helpers=[helper], tasks=[pending], accounts=[_acc("C1"), _acc("P1", warm=True)],
                enrollments=[("C1", WarmupState.RECEIVING.value, True)], config=config)
    res = await he.run_helper_tick(db, now=TEHRAN_11AM, client_factory=lambda *a: MagicMock())
    assert res["acted"] == 0 and res.get("throttled") is True


# ── wa.me link resolved via getWaSettings when accounts.phone is null ─────────
@pytest.mark.asyncio
async def test_resolve_cold_phone_backfills_from_wasettings():
    cold = _acc("C1"); cold.phone = None      # partner/QR flow leaves phone null
    db = FakeDB(accounts=[cold])
    def factory(iid, tok):
        c = MagicMock()
        c.get_wa_settings = AsyncMock(return_value={"phone": "989048249532"})
        return c
    digits, acc = await he._resolve_cold_phone(db, "C1", factory)
    assert digits == "989048249532"
    assert hs.wa_me_link(digits) == "https://wa.me/989048249532"
    assert cold.phone == "989048249532"       # persisted back onto the account


# ── incoming from helper → task done + auto thank-you ────────────────────────
@pytest.mark.asyncio
async def test_incoming_from_helper_marks_done_and_thanks(monkeypatch):
    monkeypatch.setattr("app.services.typing_sim.asyncio.sleep", AsyncMock())
    helper = WarmupHelper(name="مریم", phone="989111111111", is_active=True)
    helper.id = uuid.uuid4()
    task = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C1", status=hs.STATUS_ASKED)
    task.id = uuid.uuid4(); task.asked_at = TEHRAN_11AM - timedelta(minutes=20)
    peer = _acc("P1", warm=True)
    db = FakeDB(helpers=[helper], tasks=[task], accounts=[peer, _acc("C1")],
                enrollments=[("C1", WarmupState.RECEIVING.value, True)])
    thanked = {}
    def factory(iid, tok):
        c = MagicMock()
        c.send_typing_ms = AsyncMock(return_value=True)
        async def _send(phone, text):
            thanked["phone"] = phone; thanked["text"] = text; return "MIDT"
        c.send_message = AsyncMock(side_effect=_send)
        return c
    res = await he.handle_helper_incoming(db, "C1", "989111111111@c.us", TEHRAN_11AM, client_factory=factory)
    assert res is not None and res["thanked"] is True
    assert task.status == hs.STATUS_DONE and task.done_at == TEHRAN_11AM
    assert thanked["phone"] == "989111111111"
    assert "ممنون" in thanked["text"]


@pytest.mark.asyncio
async def test_incoming_from_stranger_is_noop():
    helper = WarmupHelper(name="مریم", phone="989111111111", is_active=True)
    helper.id = uuid.uuid4()
    db = FakeDB(helpers=[helper], tasks=[], accounts=[_acc("P1", warm=True)])
    res = await he.handle_helper_incoming(db, "C1", "989999999999", TEHRAN_11AM,
                                          client_factory=lambda *a: MagicMock())
    assert res is None
