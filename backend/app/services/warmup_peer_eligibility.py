"""V27 PART 3 — minimum real age + clean history for warm-peer eligibility.

Fixes incident gap #3: a genuinely fresh (0-day) batch-mate was flagged `is_warm_peer=true`
and used to warm OTHER batch-mates, while an actually well-established ~14-day number sat
unused. A peer must be genuinely established, not just manually flagged.

A number may become a warm peer only when BOTH hold:
  • it has been connected for >= MIN_PEER_AGE_DAYS (14) real days, and
  • it has had NO yellowCard/blocked incident in the trailing PEER_HISTORY_WINDOW_DAYS (14).

"Connected since" is the earliest trustworthy timestamp we have for the instance: its mesh
authorized_at if enrolled, else its partner-created / added-to-system time. Pure evaluators are
unit-testable; the async wrappers load the enrollment + recent incidents from the DB.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from sqlalchemy import select, func

from app.models.account import Account
from app.models.incident import AccountIncident

MIN_PEER_AGE_DAYS = 14
PEER_HISTORY_WINDOW_DAYS = 14

# Incident types that disqualify a peer for the trailing window (health signals, not the
# warning-only throttles like low reply rate).
DISQUALIFYING_INCIDENT_TYPES = ("yellowCard", "blocked", "notAuthorized", "logout")

TOO_YOUNG_FA = (
    "این اکانت هنوز به‌اندازه‌ی کافی قدیمی/سالم نیست تا بتواند فرستنده‌ی گرم‌سازی باشد "
    "(حداقل ۱۴ روز سابقه‌ی سالم لازم است)."
)
RECENT_INCIDENT_FA = (
    "این اکانت در ۱۴ روز گذشته کارت‌زرد/مسدودی داشته و فعلاً نمی‌تواند فرستنده‌ی گرم‌سازی باشد "
    "(به یک شماره‌ی سالم با حداقل ۱۴ روز سابقه نیاز است)."
)


def connected_since(account, enrollment=None) -> datetime | None:
    """Earliest trustworthy "connected since" timestamp for an instance."""
    candidates = []
    if enrollment is not None and getattr(enrollment, "authorized_at", None):
        candidates.append(enrollment.authorized_at)
    for attr in ("partner_created_at", "created_at"):
        v = getattr(account, attr, None)
        if v:
            candidates.append(v)
    return min(candidates) if candidates else None


def peer_age_days(account, enrollment=None, now: datetime | None = None) -> float | None:
    now = now or datetime.utcnow()
    cs = connected_since(account, enrollment)
    if cs is None:
        return None
    return (now - cs).total_seconds() / 86400.0


def evaluate_peer_eligibility(account, enrollment, recent_incident_count: int,
                              now: datetime | None = None) -> tuple[bool, str, str | None]:
    """PURE. Returns (eligible, reason_slug, message_fa|None).
    reason_slug ∈ {ok, too_young, recent_incident}."""
    now = now or datetime.utcnow()
    age = peer_age_days(account, enrollment, now)
    if age is None or age < MIN_PEER_AGE_DAYS:
        return False, "too_young", TOO_YOUNG_FA
    if int(recent_incident_count or 0) > 0:
        return False, "recent_incident", RECENT_INCIDENT_FA
    return True, "ok", None


async def _recent_incident_count(db, account_id, now: datetime | None = None) -> int:
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=PEER_HISTORY_WINDOW_DAYS)
    return (await db.execute(
        select(func.count()).select_from(AccountIncident).where(
            AccountIncident.account_id == account_id,
            AccountIncident.created_at >= cutoff,
            AccountIncident.incident_type.in_(DISQUALIFYING_INCIDENT_TYPES),
        )
    )).scalar() or 0


async def check_peer_eligibility(db, account, now: datetime | None = None
                                 ) -> tuple[bool, str, str | None]:
    """Load the instance's enrollment + recent disqualifying incidents, then evaluate."""
    from app.models.warmup_mesh import WarmupEnrollment
    now = now or datetime.utcnow()
    enr = (await db.execute(
        select(WarmupEnrollment).where(WarmupEnrollment.instance_id == account.instance_id)
    )).scalar_one_or_none()
    cnt = await _recent_incident_count(db, account.id, now)
    return evaluate_peer_eligibility(account, enr, cnt, now)


async def audit_existing_peers(db, now: datetime | None = None) -> list[dict]:
    """RETROACTIVE check: report every currently-flagged warm peer that would NOT pass the
    rule today. Reports only — never auto-unflags (the user decides per number)."""
    now = now or datetime.utcnow()
    peers = (await db.execute(
        select(Account).where(Account.is_warm_peer.is_(True))
    )).scalars().all()
    failing = []
    for a in peers:
        eligible, reason, msg = await check_peer_eligibility(db, a, now)
        if not eligible:
            age = peer_age_days(a, None, now)
            failing.append({
                "instance_id": a.instance_id,
                "name": a.name,
                "phone": a.phone,
                "reason": reason,
                "message": msg,
                "age_days": round(age, 1) if age is not None else None,
            })
    return failing
