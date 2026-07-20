"""V35 PART 4 — pure gate/step logic for the guided onboarding wizard «راه‌اندازی».

The authoritative locked/unlocked state is ALWAYS derived here from the record's timestamps + the
current time, never trusted from a stored flag — so a clock change or a stale `current_step` can
never let a gate open early. Two fixed 24h gates:

  • Gate A — SIM insertion → WhatsApp activation.
  • Gate B — WhatsApp activation → Green API login.

Phases (what the page shows), with their spec step numbers:
  step 1  — "gate_a_wait": SIM recorded, waiting for Gate A to elapse (locked).
  step 2  — "activate_whatsapp": Gate A elapsed, user may bring WhatsApp up (unlocked action).
  step 3  — "gate_b_wait": WhatsApp confirmed, waiting for Gate B to elapse (locked).
  step 4  — "connect_green_api": Gate B elapsed, user connects Green API + enrolls in Team Collab.
  done    — Green API connection confirmed; onboarding complete.
"""
from datetime import datetime, timedelta

# Fixed gates (hours). Shipped as constants per the V35 spec — matches the project's proven 24h rule.
GATE_A_HOURS = 24   # SIM insertion → WhatsApp activation
GATE_B_HOURS = 24   # WhatsApp activation → Green API login

PHASE_GATE_A_WAIT = "gate_a_wait"
PHASE_ACTIVATE_WHATSAPP = "activate_whatsapp"
PHASE_GATE_B_WAIT = "gate_b_wait"
PHASE_CONNECT_GREEN_API = "connect_green_api"
PHASE_DONE = "done"

# phase → spec step number shown in the wizard.
_PHASE_STEP = {
    PHASE_GATE_A_WAIT: 1,
    PHASE_ACTIVATE_WHATSAPP: 2,
    PHASE_GATE_B_WAIT: 3,
    PHASE_CONNECT_GREEN_API: 4,
    PHASE_DONE: 4,
}


def gate_a_unlock_at(sim_inserted_at: datetime | None) -> datetime | None:
    return sim_inserted_at + timedelta(hours=GATE_A_HOURS) if sim_inserted_at else None


def gate_b_unlock_at(whatsapp_activated_at: datetime | None) -> datetime | None:
    return whatsapp_activated_at + timedelta(hours=GATE_B_HOURS) if whatsapp_activated_at else None


def derive_state(*, sim_inserted_at: datetime | None,
                 whatsapp_activated_at: datetime | None,
                 green_api_connected_at: datetime | None,
                 now: datetime) -> dict:
    """Return the authoritative wizard state for one onboarding record at `now`.

    Keys: phase, step, locked (bool), next_unlock_at (datetime|None), done (bool).
    The boundary is INCLUSIVE of the unlock instant: at exactly sim_inserted_at+24h the gate opens.
    """
    if green_api_connected_at is not None:
        return {"phase": PHASE_DONE, "step": _PHASE_STEP[PHASE_DONE],
                "locked": False, "next_unlock_at": None, "done": True}

    if whatsapp_activated_at is not None:
        unlock = gate_b_unlock_at(whatsapp_activated_at)
        if now < unlock:
            return {"phase": PHASE_GATE_B_WAIT, "step": _PHASE_STEP[PHASE_GATE_B_WAIT],
                    "locked": True, "next_unlock_at": unlock, "done": False}
        return {"phase": PHASE_CONNECT_GREEN_API, "step": _PHASE_STEP[PHASE_CONNECT_GREEN_API],
                "locked": False, "next_unlock_at": None, "done": False}

    # SIM recorded, WhatsApp not yet confirmed → Gate A.
    if sim_inserted_at is not None:
        unlock = gate_a_unlock_at(sim_inserted_at)
        if now < unlock:
            return {"phase": PHASE_GATE_A_WAIT, "step": _PHASE_STEP[PHASE_GATE_A_WAIT],
                    "locked": True, "next_unlock_at": unlock, "done": False}
        return {"phase": PHASE_ACTIVATE_WHATSAPP, "step": _PHASE_STEP[PHASE_ACTIVATE_WHATSAPP],
                "locked": False, "next_unlock_at": None, "done": False}

    # No SIM timestamp at all (defensive; the create-step always sets it).
    return {"phase": PHASE_GATE_A_WAIT, "step": 1, "locked": True,
            "next_unlock_at": None, "done": False}


def can_confirm_whatsapp(*, sim_inserted_at, whatsapp_activated_at, green_api_connected_at,
                         now: datetime) -> bool:
    """True only when the record is in the 'activate_whatsapp' phase (Gate A elapsed, not yet
    confirmed) — so a premature confirmation can never skip Gate A."""
    st = derive_state(sim_inserted_at=sim_inserted_at, whatsapp_activated_at=whatsapp_activated_at,
                      green_api_connected_at=green_api_connected_at, now=now)
    return st["phase"] == PHASE_ACTIVATE_WHATSAPP


def can_confirm_green_api(*, sim_inserted_at, whatsapp_activated_at, green_api_connected_at,
                          now: datetime) -> bool:
    """True only when the record is in the 'connect_green_api' phase (Gate B elapsed)."""
    st = derive_state(sim_inserted_at=sim_inserted_at, whatsapp_activated_at=whatsapp_activated_at,
                      green_api_connected_at=green_api_connected_at, now=now)
    return st["phase"] == PHASE_CONNECT_GREEN_API
