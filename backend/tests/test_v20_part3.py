"""V20 PART 3 — dashboard roles + no-peer notice.

Asserts the dashboard reports the correct ROLE per account (being-warmed / peer-sender /
graduated / none), surfaces the no-peer notice when no warm sender is marked, and shows
which peers warm each cold number (edges).
"""
import uuid
from datetime import datetime
from types import SimpleNamespace
import pytest

from app.services.warmup_dashboard import (
    build_number_card, build_dashboard, NO_PEER_NOTICE, ROLE_LABELS_FA,
)
from app.services.warmup_state import WarmupState

NOW = datetime(2026, 5, 20, 12, 0, 0)


def _enr(instance_id="COLD", state="RECEIVING", **kw):
    base = dict(instance_id=instance_id, phone="989120000001", state=state,
                sent_today=0, received_today=0, reply_ratio=0.0, is_enabled=True,
                next_action_at=None, rest_until=None,
                authorized_at=datetime(2026, 5, 18, 9, 0), started_at=datetime(2026, 5, 18, 9, 0))
    base.update(kw)
    e = SimpleNamespace(**base); e.id = uuid.uuid4()
    return e


def _edge(peer, active=True):
    return SimpleNamespace(peer_instance_id=peer, msg_count=1, last_msg_at=NOW, id=uuid.uuid4(),
                           saved_as_contact_new=active, saved_as_contact_peer=active,
                           handshake_state="active" if active else "none")


# ── card role + no-peer notice ──────────────────────────────────────────────
def test_card_role_being_warmed():
    card = build_number_card(_enr(state="RAMPING"), [_edge("P")], NOW)
    assert card["role"] == "being_warmed"


def test_card_role_graduated_peer():
    card = build_number_card(_enr(state="GRADUATED", authorized_at=datetime(2026, 4, 1),
                                  started_at=datetime(2026, 4, 1)), [], NOW)
    assert card["role"] == "graduated_peer"


def test_card_no_peer_notice_when_no_eligible_peer():
    # active state, 0 messageable edges, and no eligible peer marked → the specific notice
    card = build_number_card(_enr(state="RECEIVING"), [], NOW, has_eligible_peer=False)
    assert card["banner"]["type"] == "no_peer"
    assert card["banner"]["message"] == NO_PEER_NOTICE


def test_card_insufficient_when_peer_exists_but_edges_building():
    # peers exist (has_eligible_peer=True) but edges not built yet → building message, not no_peer
    card = build_number_card(_enr(state="RECEIVING"), [], NOW, has_eligible_peer=True)
    assert card["banner"]["type"] == "insufficient_peers"


def test_card_shows_warming_peers_via_edges():
    card = build_number_card(_enr(state="RAMPING"), [_edge("WARM", active=True)], NOW,
                             has_eligible_peer=True)
    assert card["messageable_peer_count"] == 1
    assert card["peers"][0]["peer_instance_id"] == "WARM"
    assert card["banner"] is None       # has a live peer → no banner


# ── dashboard roles overview + peer availability ────────────────────────────
def test_dashboard_roles_and_no_peer_flag():
    enr = _enr("COLD", state="RECEIVING")
    roles = [
        {"instance_id": "COLD", "name": "cold", "role": "being_warmed"},
        {"instance_id": "WARM", "name": "warm-sender", "role": "peer_sender"},
        {"instance_id": "X", "name": "x", "role": "none"},
    ]
    dash = build_dashboard([enr], {"COLD": []}, now=NOW,
                           has_eligible_peer=True, roles=roles)
    assert dash["warm_peer_count"] == 1
    assert dash["has_eligible_peer"] is True and dash["no_peer_notice"] is None
    # role labels attached
    warm = next(r for r in dash["roles"] if r["instance_id"] == "WARM")
    assert warm["role_label"] == ROLE_LABELS_FA["peer_sender"]


def test_dashboard_no_peer_notice_when_zero_senders():
    enr = _enr("COLD", state="RECEIVING")
    roles = [{"instance_id": "COLD", "name": "cold", "role": "being_warmed"}]
    dash = build_dashboard([enr], {"COLD": []}, now=NOW,
                           has_eligible_peer=False, roles=roles)
    assert dash["warm_peer_count"] == 0
    assert dash["has_eligible_peer"] is False
    assert dash["no_peer_notice"] == NO_PEER_NOTICE
    # the enrolled cold number's card also carries the no-peer banner
    assert dash["numbers"][0]["banner"]["type"] == "no_peer"


def test_dashboard_counts_graduated_as_peer():
    roles = [
        {"instance_id": "G", "name": "grad", "role": "graduated_peer"},
        {"instance_id": "WARM", "name": "warm", "role": "peer_sender"},
    ]
    dash = build_dashboard([], {}, now=NOW, has_eligible_peer=True, roles=roles)
    assert dash["warm_peer_count"] == 2      # both graduated + explicit peer count as senders
