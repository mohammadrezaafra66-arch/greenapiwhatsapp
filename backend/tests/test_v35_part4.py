"""V35 PART 4 — guided onboarding wizard «راه‌اندازی»: the two 24h gates + step flow.

The locked/unlocked state is derived purely from the record's timestamps + now, so these tests
mock time to prove: the page stays locked until Gate A's 24h elapses and unlocks EXACTLY at the
boundary; confirming step 2 sets whatsapp_activated_at and starts Gate B; step 4 unlocks exactly
at Gate B's boundary; and completion is terminal. Also verifies the confirm-gates refuse early.
"""
from datetime import datetime, timedelta

from app.services import onboarding_service as ob
from app.models.account_onboarding import AccountOnboarding


SIM = datetime(2026, 3, 1, 9, 0, 0)   # arbitrary fixed base time (naive UTC)


def _state(sim=None, wa=None, green=None, now=None):
    return ob.derive_state(sim_inserted_at=sim, whatsapp_activated_at=wa,
                           green_api_connected_at=green, now=now)


# ── gate constants ────────────────────────────────────────────────────────────
def test_gate_constants_are_24h():
    assert ob.GATE_A_HOURS == 24
    assert ob.GATE_B_HOURS == 24


# ── Gate A: locked until 24h, unlocks exactly at the boundary ─────────────────
def test_gate_a_locked_before_24h():
    st = _state(sim=SIM, now=SIM + timedelta(hours=23, minutes=59))
    assert st["phase"] == ob.PHASE_GATE_A_WAIT
    assert st["step"] == 1 and st["locked"] is True
    assert st["next_unlock_at"] == SIM + timedelta(hours=24)


def test_gate_a_unlocks_exactly_at_boundary():
    # At exactly SIM+24h the gate is OPEN (boundary inclusive).
    st = _state(sim=SIM, now=SIM + timedelta(hours=24))
    assert st["phase"] == ob.PHASE_ACTIVATE_WHATSAPP
    assert st["step"] == 2 and st["locked"] is False
    assert st["next_unlock_at"] is None


def test_gate_a_one_second_before_boundary_still_locked():
    st = _state(sim=SIM, now=SIM + timedelta(hours=24) - timedelta(seconds=1))
    assert st["locked"] is True and st["phase"] == ob.PHASE_GATE_A_WAIT


# ── Step 2 confirmation starts Gate B ─────────────────────────────────────────
def test_confirm_whatsapp_only_allowed_after_gate_a():
    # Before Gate A → refused.
    assert ob.can_confirm_whatsapp(sim_inserted_at=SIM, whatsapp_activated_at=None,
                                   green_api_connected_at=None,
                                   now=SIM + timedelta(hours=1)) is False
    # After Gate A → allowed.
    assert ob.can_confirm_whatsapp(sim_inserted_at=SIM, whatsapp_activated_at=None,
                                   green_api_connected_at=None,
                                   now=SIM + timedelta(hours=25)) is True


def test_after_whatsapp_confirmed_gate_b_starts():
    wa = SIM + timedelta(hours=25)          # confirmed 1h after Gate A opened
    st = _state(sim=SIM, wa=wa, now=wa + timedelta(hours=1))
    assert st["phase"] == ob.PHASE_GATE_B_WAIT
    assert st["step"] == 3 and st["locked"] is True
    assert st["next_unlock_at"] == wa + timedelta(hours=24)


# ── Gate B: unlocks exactly at the boundary → step 4 ──────────────────────────
def test_gate_b_unlocks_exactly_at_boundary():
    wa = SIM + timedelta(hours=25)
    st = _state(sim=SIM, wa=wa, now=wa + timedelta(hours=24))
    assert st["phase"] == ob.PHASE_CONNECT_GREEN_API
    assert st["step"] == 4 and st["locked"] is False


def test_gate_b_before_boundary_locked():
    wa = SIM + timedelta(hours=25)
    st = _state(sim=SIM, wa=wa, now=wa + timedelta(hours=23, minutes=59))
    assert st["locked"] is True and st["phase"] == ob.PHASE_GATE_B_WAIT


def test_confirm_green_api_only_allowed_after_gate_b():
    wa = SIM + timedelta(hours=25)
    assert ob.can_confirm_green_api(sim_inserted_at=SIM, whatsapp_activated_at=wa,
                                    green_api_connected_at=None,
                                    now=wa + timedelta(hours=1)) is False
    assert ob.can_confirm_green_api(sim_inserted_at=SIM, whatsapp_activated_at=wa,
                                    green_api_connected_at=None,
                                    now=wa + timedelta(hours=25)) is True


# ── Completion is terminal ────────────────────────────────────────────────────
def test_done_state_when_green_connected():
    wa = SIM + timedelta(hours=25)
    green = wa + timedelta(hours=25)
    st = _state(sim=SIM, wa=wa, green=green, now=green + timedelta(days=3))
    assert st["phase"] == ob.PHASE_DONE
    assert st["done"] is True and st["locked"] is False
    assert st["next_unlock_at"] is None


# ── model column shape ────────────────────────────────────────────────────────
def test_model_columns():
    cols = AccountOnboarding.__table__.columns.keys()
    for c in ("phone_number", "phone_make_model", "sim_inserted_at", "whatsapp_activated_at",
              "green_api_login_prompted_at", "green_api_connected_at", "current_step", "created_at"):
        assert c in cols


# ── multiple in-progress onboardings derive independently (list view) ─────────
def test_multiple_onboardings_independent_states():
    now = SIM + timedelta(hours=30)
    a = _state(sim=SIM, now=now)                                   # Gate A elapsed → step 2
    b = _state(sim=SIM + timedelta(hours=20), now=now)            # only 10h in → Gate A wait
    assert a["phase"] == ob.PHASE_ACTIVATE_WHATSAPP
    assert b["phase"] == ob.PHASE_GATE_A_WAIT
    assert b["next_unlock_at"] == SIM + timedelta(hours=20) + timedelta(hours=24)
