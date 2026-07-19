"""V29 «همکاری تیمی» PART 8 — sender WARMTH score/analysis.

V27 PART 3 gave a BINARY warm-peer gate (>= 14 real days AND a clean 14-day history). V29 turns
that into a graded 0–100 score + a Persian level (کم / متوسط / بالا) so the dashboard shows HOW
warm a candidate sender actually is, not just pass/fail. The score composes three signals:

  • age            (0–50)  — days since the account was first connected, saturating at the same
                             14-day floor V27 uses;
  • incident-free  (0–30)  — a clean trailing 14-day window (any yellowCard/blocked/… zeroes it);
  • recent activity(0–20)  — how recently the account was active (fresh traffic = warmer).

The pure `compute_warmth` is fully unit-tested; the async wrapper loads the age/incidents/
activity from the DB (reusing V27's own evaluators so the two never drift).
"""
from __future__ import annotations
from datetime import datetime, timedelta

from app.services.warmup_peer_eligibility import (
    MIN_PEER_AGE_DAYS, connected_since, peer_age_days, evaluate_peer_eligibility,
    _recent_incident_count,
)

# Component ceilings.
AGE_MAX = 50
INCIDENT_MAX = 30
ACTIVITY_MAX = 20

# Level thresholds (0–100).
LEVEL_HIGH_MIN = 70
LEVEL_MID_MIN = 40

LEVEL_HIGH_FA = "بالا"
LEVEL_MID_FA = "متوسط"
LEVEL_LOW_FA = "کم"

# Recent-activity windows (days).
ACTIVITY_FRESH_DAYS = 7
ACTIVITY_OK_DAYS = 14


def _age_score(age_days: float | None) -> int:
    if age_days is None or age_days <= 0:
        return 0
    return round(min(age_days / MIN_PEER_AGE_DAYS, 1.0) * AGE_MAX)


def _incident_score(recent_incident_count: int) -> int:
    # A clean trailing window earns the full component; ANY disqualifying incident zeroes it.
    return INCIDENT_MAX if int(recent_incident_count or 0) == 0 else 0


def _activity_score(days_since_activity: float | None) -> int:
    if days_since_activity is None:
        return 0
    if days_since_activity <= ACTIVITY_FRESH_DAYS:
        return ACTIVITY_MAX
    if days_since_activity <= ACTIVITY_OK_DAYS:
        return ACTIVITY_MAX // 2
    return 0


def level_for_score(score: int) -> str:
    if score >= LEVEL_HIGH_MIN:
        return LEVEL_HIGH_FA
    if score >= LEVEL_MID_MIN:
        return LEVEL_MID_FA
    return LEVEL_LOW_FA


def compute_warmth(*, age_days: float | None, recent_incident_count: int,
                   days_since_activity: float | None, eligible: bool | None = None) -> dict:
    """PURE. Compose the 0–100 warmth score + level from the three signals.

    A sender that FAILS V27's binary gate (too young or a recent incident) is capped BELOW «بالا»
    even if the arithmetic would round up — «بالا» must imply the account already passes the gate."""
    age = _age_score(age_days)
    inc = _incident_score(recent_incident_count)
    act = _activity_score(days_since_activity)
    score = age + inc + act
    if eligible is False:
        score = min(score, LEVEL_HIGH_MIN - 1)   # never «بالا» unless it passes the V27 gate
    score = max(0, min(100, score))
    return {"score": score, "level": level_for_score(score),
            "components": {"age": age, "incident_free": inc, "activity": act}}


async def warmth_for_account(db, account, now: datetime | None = None) -> dict:
    """Load the account's age (mesh authorized_at / created_at), trailing-14d disqualifying
    incidents, and last-activity, then compute the warmth score. Reuses V27's evaluators."""
    from app.models.warmup_mesh import WarmupEnrollment
    from sqlalchemy import select
    now = now or datetime.utcnow()
    enr = (await db.execute(
        select(WarmupEnrollment).where(WarmupEnrollment.instance_id == account.instance_id)
    )).scalar_one_or_none()
    age = peer_age_days(account, enr, now)
    incidents = await _recent_incident_count(db, account.id, now)
    eligible, reason, _msg = evaluate_peer_eligibility(account, enr, incidents, now)

    last_activity = getattr(enr, "last_activity_at", None) if enr else None
    if last_activity is None:
        last_activity = getattr(account, "last_activity_at", None)
    days_since = ((now - last_activity).total_seconds() / 86400.0
                  if last_activity is not None else None)

    out = compute_warmth(age_days=age, recent_incident_count=incidents,
                         days_since_activity=days_since, eligible=eligible)
    out.update({"instance_id": account.instance_id, "name": getattr(account, "name", None),
                "eligible": bool(eligible), "reason": reason,
                "age_days": round(age, 1) if age is not None else None,
                "recent_incidents": int(incidents or 0)})
    return out


async def warmth_for_all_senders(db, now: datetime | None = None) -> list[dict]:
    """Warmth for every active account (any account can be an outreach sender)."""
    from sqlalchemy import select
    from app.models.account import Account, AccountStatus
    now = now or datetime.utcnow()
    accounts = (await db.execute(
        select(Account).where(Account.status == AccountStatus.active).order_by(Account.created_at)
    )).scalars().all()
    return [await warmth_for_account(db, a, now) for a in accounts]
