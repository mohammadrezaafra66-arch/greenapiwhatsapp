"""V17 PART 6 — warm-up dashboard (data + controls).

Tests the dashboard payload builder (state/day/progress/counts/ratio/peers/next-action/
badge/banners) and the per-number controls (pause/resume/restart) at the service layer,
matching the repo's DB-free test style.
"""
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

from app.models.account import Account, AccountStatus
from app.models.warmup_mesh import WarmupEnrollment
from app.services.warmup_dashboard import (
    build_number_card, build_dashboard, display_daily_target, GRADUATE_DAY, STATE_LABELS_FA,
)
from app.services.warmup_state import WarmupState
from app.services import warmup_mesh_service as svc


NOW = datetime(2026, 5, 1, 12, 0, 0)


def _enr(**kw):
    base = dict(instance_id="NEW", phone="989120000001", state="RAMPING",
                sent_today=8, received_today=10, reply_ratio=0.8, is_enabled=True,
                next_action_at=datetime(2026, 5, 1, 13, 0, 0), rest_until=None,
                authorized_at=datetime(2026, 4, 25, 9, 0, 0), started_at=datetime(2026, 4, 25, 9, 0, 0))
    base.update(kw)
    e = SimpleNamespace(**base)
    e.id = kw.get("id", uuid.uuid4())
    return e


def _edge(peer, active=True, msg_count=3):
    e = SimpleNamespace(new_instance_id="NEW", peer_instance_id=peer, msg_count=msg_count,
                        last_msg_at=NOW, id=uuid.uuid4())
    e.saved_as_contact_new = active
    e.saved_as_contact_peer = active
    e.handshake_state = "active" if active else "none"
    return e


# ── display_daily_target per stage ───────────────────────────────────────────
def test_display_target_per_state():
    # day 7 (RAMPING) → ramp_curve[3] = 48
    e = _enr(state="RAMPING")
    assert display_daily_target(e, NOW) == 48
    # COOLDOWN → 0
    c = _enr(state="COOLDOWN", authorized_at=datetime(2026, 5, 1, 8, 0, 0),
             started_at=datetime(2026, 5, 1, 8, 0, 0))
    assert display_daily_target(c, NOW) == 0
    # MATURING → representative 100 (RNG-free)
    m = _enr(state="MATURING", authorized_at=datetime(2026, 4, 15), started_at=datetime(2026, 4, 15))
    assert display_daily_target(m, NOW) == 100


# ── build_number_card ────────────────────────────────────────────────────────
def test_card_core_fields():
    e = _enr(state="RAMPING")
    edges = [_edge("P1", active=True), _edge("P2", active=False)]
    card = build_number_card(e, edges, NOW)
    assert card["instance_id"] == "NEW"
    assert card["state"] == "RAMPING"
    assert card["badge"] == STATE_LABELS_FA["RAMPING"]
    assert card["day_index"] == 7                      # 6 full days since 04-25 + 1
    assert card["sent_today"] == 8 and card["received_today"] == 10
    assert card["reply_ratio"] == 0.8 and card["reply_ratio_ok"] is True
    assert card["day_target"] == 48
    assert card["next_action_at"] == "2026-05-01T13:00:00"
    # progress toward graduation
    assert card["graduate_day"] == GRADUATE_DAY
    assert card["progress_pct"] == int(round(7 / GRADUATE_DAY * 100))
    # peers + per-edge activity; only P1 is messageable
    assert card["peer_count"] == 2 and card["messageable_peer_count"] == 1
    p1 = next(p for p in card["peers"] if p["peer_instance_id"] == "P1")
    assert p1["messageable"] is True and p1["msg_count"] == 3


def test_card_graduated_is_full_progress():
    e = _enr(state="GRADUATED", authorized_at=datetime(2026, 3, 1), started_at=datetime(2026, 3, 1))
    card = build_number_card(e, [], NOW)
    assert card["progress_pct"] == 100


def test_card_paused_banner():
    card = build_number_card(_enr(state="PAUSED"), [_edge("P1")], NOW)
    assert card["banner"]["type"] == "paused"


def test_card_yellowcard_banner():
    card = build_number_card(_enr(state="YELLOWCARD"), [_edge("P1")], NOW)
    assert card["banner"]["type"] == "yellowcard"


def test_card_insufficient_peers_banner():
    # active stage but no messageable edges → insufficient-peers notice
    card = build_number_card(_enr(state="RECEIVING"), [_edge("P1", active=False)], NOW)
    assert card["banner"]["type"] == "insufficient_peers"


def test_card_low_ratio_flagged():
    card = build_number_card(_enr(state="RAMPING", reply_ratio=0.3), [_edge("P1")], NOW)
    assert card["reply_ratio_ok"] is False


# ── V21 PART 1 — capacity-full banner + assigned peer ────────────────────────
def test_card_capacity_full_banner():
    # no peer edge at all + every warm peer at cap → capacity-full notice (even in COOLDOWN)
    card = build_number_card(_enr(state="COOLDOWN"), [], NOW, capacity_full=True)
    assert card["banner"]["type"] == "capacity_full"
    assert card["capacity_full"] is True
    assert card["assigned_peer"] is None


def test_card_assigned_peer_reported():
    card = build_number_card(_enr(state="RAMPING"), [_edge("P7")], NOW)
    assert card["assigned_peer"] == "P7"
    assert card["capacity_full"] is False


def test_card_capacity_full_ignored_when_peer_present():
    # if the number already has an edge, capacity_full must NOT mask it
    card = build_number_card(_enr(state="RAMPING"), [_edge("P1")], NOW, capacity_full=True)
    assert card["capacity_full"] is False
    assert (card["banner"] or {}).get("type") != "capacity_full"


def test_card_not_connected_banner_top_priority():
    # even a PAUSED number shows the connect-first notice when not connected
    card = build_number_card(_enr(state="PAUSED"), [], NOW, not_connected=True)
    assert card["banner"]["type"] == "not_connected"
    assert card["not_connected"] is True


def test_dashboard_marks_not_connected_instance():
    e1 = _enr(instance_id="A", state="COOLDOWN")
    e2 = _enr(instance_id="B", state="RAMPING")
    dash = build_dashboard([e1, e2], {"A": [], "B": [_edge("HUB")]}, now=NOW,
                           not_connected_instances={"A"})
    a = next(c for c in dash["numbers"] if c["instance_id"] == "A")
    b = next(c for c in dash["numbers"] if c["instance_id"] == "B")
    assert a["banner"]["type"] == "not_connected" and a["not_connected"] is True
    assert b["not_connected"] is False


def test_dashboard_carries_peer_load_and_cap():
    e1 = _enr(instance_id="A", state="RAMPING")
    dash = build_dashboard([e1], {"A": [_edge("HUB")]}, now=NOW,
                           peer_load=[{"instance_id": "HUB", "name": "hub", "cold_count": 1,
                                       "cap": 2, "full": False}])
    assert dash["max_cold_per_warm_peer"] == 2
    assert dash["peer_load"][0]["cold_count"] == 1 and dash["peer_load"][0]["cap"] == 2


# ── build_dashboard ──────────────────────────────────────────────────────────
def test_dashboard_aggregates_and_breaker_banner():
    e1 = _enr(instance_id="A", state="RAMPING")
    e2 = _enr(instance_id="B", state="RECEIVING")
    edges = {"A": [_edge("HUB")], "B": [_edge("HUB")]}
    dash = build_dashboard([e1, e2], edges, breaker_tripped=True, now=NOW)
    assert dash["total"] == 2 and len(dash["numbers"]) == 2
    assert dash["breaker_tripped"] is True
    assert dash["global_banner"]["type"] == "breaker"


def test_dashboard_no_breaker_no_global_banner():
    dash = build_dashboard([_enr()], {"NEW": [_edge("P1")]}, breaker_tripped=False, now=NOW)
    assert dash["breaker_tripped"] is False and dash["global_banner"] is None


# ── controls: resume + restart ───────────────────────────────────────────────
class FakeScalars:
    def __init__(self, items): self._items = list(items)
    def all(self): return list(self._items)


class FakeResult:
    def __init__(self, scalars=None): self._scalars = scalars if scalars is not None else []
    def scalars(self): return FakeScalars(self._scalars)
    def scalar_one_or_none(self): return self._scalars[0] if self._scalars else None


class FakeSession:
    def __init__(self, results=None):
        self._results = list(results or [])
        self.added = []
        self.commits = 0
    async def execute(self, q): return self._results.pop(0) if self._results else FakeResult()
    def add(self, o): self.added.append(o)
    async def commit(self): self.commits += 1


def _account():
    a = Account(name="n", instance_id="NEW", api_token="t")
    a.id = uuid.uuid4(); a.phone = "989120000001"; a.status = AccountStatus.active
    return a


@pytest.mark.asyncio
async def test_resume_reenables_and_leaves_paused_state():
    enr = WarmupEnrollment(instance_id="NEW", state=WarmupState.PAUSED.value)
    enr.id = uuid.uuid4(); enr.is_enabled = False
    enr.authorized_at = datetime(2026, 4, 25); enr.started_at = datetime(2026, 4, 25)
    db = FakeSession(results=[FakeResult(scalars=[enr])])
    res = await svc.resume_warmup(db, _account(), now=NOW)
    assert res["resumed"] is True
    assert enr.is_enabled is True
    assert enr.state != WarmupState.PAUSED.value       # moved back into the live flow
    assert db.commits == 1


@pytest.mark.asyncio
async def test_force_restart_resets_to_day_one():
    enr = WarmupEnrollment(instance_id="NEW", state=WarmupState.RAMPING.value)
    enr.id = uuid.uuid4(); enr.is_enabled = True
    enr.day_index = 7; enr.sent_today = 40; enr.received_today = 42
    db = FakeSession(results=[FakeResult(scalars=[enr])])
    res = await svc.force_restart(db, _account(), now=NOW)
    assert res["restarted"] is True
    assert enr.state == WarmupState.COOLDOWN.value
    assert enr.day_index == 0 and enr.sent_today == 0 and enr.received_today == 0
    assert enr.authorized_at == NOW
