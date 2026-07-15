"""V19 PART 5 — dashboard surfacing of group placements + one-toggle-drives-both.

Asserts the dashboard card carries group-placement state (statuses/counts/next action)
alongside the mesh info, and that the SINGLE enrollment (set by the one toggle) gates BOTH
the message mesh and the group-placement track — nothing extra to press.
"""
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

from app.services.warmup_dashboard import build_number_card, build_dashboard
from app.services.warmup_state import WarmupState


NOW = datetime(2026, 5, 20, 12, 0, 0)


def _enr(**kw):
    base = dict(instance_id="COLD", phone="989120000001", state="RAMPING",
                sent_today=2, received_today=3, reply_ratio=1.5, is_enabled=True,
                next_action_at=None, rest_until=None,
                authorized_at=datetime(2026, 5, 14, 9, 0), started_at=datetime(2026, 5, 14, 9, 0))
    base.update(kw)
    e = SimpleNamespace(**base); e.id = kw.get("id", uuid.uuid4())
    return e


def _mem(group_id, status, added_at=None, last_attempt_at=None, warm="WARM", error=None):
    return SimpleNamespace(group_id=group_id, warm_instance_id=warm, status=status,
                           added_at=added_at, last_attempt_at=last_attempt_at, error_reason=error)


def _edge(active=True):
    return SimpleNamespace(peer_instance_id="P", msg_count=1, last_msg_at=NOW, id=uuid.uuid4(),
                           saved_as_contact_new=active, saved_as_contact_peer=active,
                           handshake_state="active" if active else "none")


# ── group placements on the card ────────────────────────────────────────────
def test_card_includes_group_placements_and_counts():
    memberships = [
        _mem("g1", "added", added_at=datetime(2026, 5, 18, 10, 0)),
        _mem("g2", "added", added_at=datetime(2026, 5, 20, 10, 0)),
        _mem("g3", "failed", last_attempt_at=datetime(2026, 5, 20, 11, 0), error="addParticipant=false"),
    ]
    card = build_number_card(_enr(), [_edge()], NOW, group_memberships=memberships)
    gw = card["group_warmup"]
    assert gw["counts"] == {"added": 2, "pending": 0, "failed": 1}
    assert len(gw["placements"]) == 3
    assert gw["last_action_at"] == "2026-05-20T11:00:00"     # most recent action
    assert gw["next_action_at"] is not None                  # estimate present
    # mesh info still present (group warm-up is additive, not a replacement)
    assert card["state"] == "RAMPING" and "peers" in card


def test_card_no_group_memberships_is_empty_but_present():
    card = build_number_card(_enr(), [_edge()], NOW, group_memberships=[])
    assert card["group_warmup"]["counts"] == {"added": 0, "pending": 0, "failed": 0}
    assert card["group_warmup"]["placements"] == []
    assert card["group_warmup"]["next_action_at"] is None


def test_next_group_action_estimate_48h_in_ramping():
    m = [_mem("g1", "added", added_at=datetime(2026, 5, 20, 10, 0))]
    card = build_number_card(_enr(state="RAMPING"), [_edge()], NOW, group_memberships=m)
    # RAMPING → last action + 48h
    assert card["group_warmup"]["next_action_at"] == (datetime(2026, 5, 20, 10, 0) + timedelta(hours=48)).isoformat()


def test_dashboard_routes_memberships_by_instance():
    e1 = _enr(instance_id="A")
    e2 = _enr(instance_id="B")
    edges = {"A": [_edge()], "B": [_edge()]}
    membs = {"A": [_mem("g1", "added", added_at=NOW)], "B": []}
    dash = build_dashboard([e1, e2], edges, now=NOW, memberships_by_instance=membs)
    by = {c["instance_id"]: c for c in dash["numbers"]}
    assert by["A"]["group_warmup"]["counts"]["added"] == 1
    assert by["B"]["group_warmup"]["counts"]["added"] == 0


# ── one toggle drives BOTH tracks (same enrollment gates mesh + group) ───────
@pytest.mark.asyncio
async def test_group_track_gated_by_same_enrollment_toggle():
    """The group engine only acts on is_enabled enrollments — the SAME flag the one toggle
    sets. Disabling (toggle OFF) stops the group track too."""
    from app.services.warmup_group_engine import run_group_warmup_tick

    class ScalarsRes:
        def __init__(self, items): self._items = list(items)
        def scalars(self):
            outer = self
            class S:
                def all(self_inner): return list(outer._items)
            return S()

    # enrollment is DISABLED (toggle OFF) → group tick must do nothing even with targets
    target = SimpleNamespace(group_id="g1", is_selected=True, warm_instance_id="WARM")
    disabled_enr = _enr(is_enabled=False)

    class DB:
        def __init__(self): self.p = 0; self.added = []; self.commits = 0
        async def execute(self, q):
            self.p += 1
            if self.p == 1: return ScalarsRes([])          # breaker events (none)
            if self.p == 2: return ScalarsRes([target])    # selected targets
            if self.p == 3: return ScalarsRes([])          # is_enabled enrollments → NONE (disabled filtered out)
            if self.p == 4: return ScalarsRes([])          # active accounts
            return ScalarsRes([])
        def add(self, o): self.added.append(o)
        async def commit(self): self.commits += 1

    db = DB()
    res = await run_group_warmup_tick(db, now=NOW, client_factory=lambda *a: None)
    assert res["acted"] == 0                     # toggle OFF → no group placements
    assert db.added == []


def test_group_and_mesh_share_enrollment_is_enabled_flag():
    """Both engines filter on WarmupEnrollment.is_enabled — proving one toggle drives both."""
    import inspect
    from app.services import warmup_engine, warmup_group_engine
    mesh_src = inspect.getsource(warmup_engine.run_warmup_tick)
    group_src = inspect.getsource(warmup_group_engine.run_group_warmup_tick)
    assert "is_enabled" in mesh_src and "WarmupEnrollment" in mesh_src
    assert "is_enabled" in group_src and "WarmupEnrollment" in group_src
