"""V39 PART 2/3 — the hard Team-Collaboration SENDER-eligibility gate, with a logged override.

Until V39 the ≥14-day-connected + clean-14-day-incident-history bar (V27 PART 3 / V30 PART 8) was
only a DISPLAYED warmth score — nothing stopped assigning or using a too-young / recently-incident
account as a Team Collaboration sender. This module turns that computation into an ENFORCED gate:

  • at ASSIGNMENT time (PART 2): `enforce_for_assignment` — rejects designating an ineligible
    account as a sender with a SPECIFIC Persian reason (exact days short, or a recent incident),
    unless the request carries an explicit override (a flag + a required note), which is PERSISTED
    on warmup_sender_config AND written to the Team-Collaboration audit log;
  • at SEND time (PART 3): `sender_send_allowed` — defense-in-depth for data that bypassed the API
    (a direct DB edit / a pre-V39 legacy assignment): a sender may send only if it is eligible OR
    carries a valid logged override.

The eligibility computation itself is REUSED from warmup_peer_eligibility (single source of truth),
never reimplemented. All user-facing strings are Persian.
"""
from __future__ import annotations
import logging
from datetime import datetime

from sqlalchemy import select

from app.models.account import Account
from app.models.warmup_helpers import WarmupSenderConfig
from app.models.warmup_mesh import WarmupEnrollment
from app.services.warmup_peer_eligibility import (
    evaluate_peer_eligibility, peer_age_days, _recent_incident_count, MIN_PEER_AGE_DAYS,
)
from app.services import warmup_helper_log as tclog

logger = logging.getLogger("afrakala.sender_eligibility")

DEFAULT_OVERRIDER = "admin"   # no auth/user model in this single-admin panel; recorded for audit.

# Western → Persian digits, so the exact-day message reads naturally in the RTL UI.
_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _fa(value) -> str:
    return str(value).translate(_FA_DIGITS)


def too_young_message_fa(age_days: float | None) -> str:
    a = round(age_days, 1) if age_days is not None else 0.0
    return (f"این اکانت فقط {_fa(a)} روز از اتصالش گذشته — "
            f"حداقل {_fa(MIN_PEER_AGE_DAYS)} روز سابقه‌ی سالم لازم است.")


RECENT_INCIDENT_MESSAGE_FA = (
    "این اکانت در ۱۴ روز اخیر حادثه (کارت‌زرد/مسدودی) داشته و فعلاً نمی‌تواند "
    "فرستنده‌ی همکاری تیمی باشد — به یک شماره‌ی سالم با حداقل ۱۴ روز سابقه نیاز است."
)
NOT_FOUND_MESSAGE_FA = "اکانت فرستنده یافت نشد."
NOTE_REQUIRED_FA = "برای رد شرط ۱۴روزه، نوشتن یک یادداشت کوتاه (دلیل) الزامی است."
GENERIC_INELIGIBLE_FA = "این اکانت واجد شرایط فرستنده‌ی همکاری تیمی نیست."


async def _load_sender(db, sender_instance_id: str) -> Account | None:
    return (await db.execute(
        select(Account).where(Account.instance_id == sender_instance_id))).scalar_one_or_none()


async def _load_config(db, sender_instance_id: str) -> WarmupSenderConfig | None:
    return (await db.execute(
        select(WarmupSenderConfig).where(
            WarmupSenderConfig.sender_instance_id == sender_instance_id).limit(1)
    )).scalar_one_or_none()


def override_active(cfg) -> bool:
    """True when a sender's config row carries a recorded eligibility override."""
    return cfg is not None and getattr(cfg, "eligibility_overridden_at", None) is not None


async def has_valid_override(db, sender_instance_id: str | None) -> bool:
    if not sender_instance_id:
        return False
    return override_active(await _load_config(db, sender_instance_id))


async def check_sender_eligibility(db, sender_instance_id: str,
                                   now: datetime | None = None) -> tuple[bool, str, str | None, float | None]:
    """Authoritative eligibility for the TC SENDER role. Returns
    (eligible, reason_slug, message_fa|None, age_days). Reuses the V27 evaluator + age computation
    against the SAME enrollment/incident data, so the reported day count matches the decision.
    reason ∈ {ok, too_young, recent_incident, not_found}."""
    now = now or datetime.utcnow()
    acc = await _load_sender(db, sender_instance_id)
    if acc is None:
        return False, "not_found", NOT_FOUND_MESSAGE_FA, None
    enr = (await db.execute(
        select(WarmupEnrollment).where(WarmupEnrollment.instance_id == sender_instance_id)
    )).scalar_one_or_none()
    incidents = await _recent_incident_count(db, acc.id, now)
    eligible, reason, _msg = evaluate_peer_eligibility(acc, enr, incidents, now)
    age = peer_age_days(acc, enr, now)
    if eligible:
        return True, "ok", None, age
    if reason == "too_young":
        return False, reason, too_young_message_fa(age), age
    if reason == "recent_incident":
        return False, reason, RECENT_INCIDENT_MESSAGE_FA, age
    return False, reason, GENERIC_INELIGIBLE_FA, age


async def record_override(db, sender_instance_id: str, note: str, *,
                          by: str = DEFAULT_OVERRIDER, reason: str | None = None,
                          now: datetime | None = None) -> WarmupSenderConfig:
    """Persist a deliberate eligibility override on the sender's config AND write an auditable
    Team-Collaboration log entry (who/when/which account/why). Does NOT commit (the caller's
    assignment commit persists it), consistent with the rest of the assignment flow."""
    now = now or datetime.utcnow()
    from app.services import warmup_helper_service as hs
    cfg = await hs.get_sender_config(db, sender_instance_id)   # lazily creates (default ON), flushes
    cfg.eligibility_overridden_at = now
    cfg.eligibility_override_note = (note or "").strip()
    cfg.eligibility_overridden_by = by or DEFAULT_OVERRIDER
    tclog.record(
        db, event_type=tclog.EVENT_ELIGIBILITY_OVERRIDE,
        from_instance_id=sender_instance_id, sender_instance_id=sender_instance_id,
        message_sent=f"[override reason={reason or 'ineligible'} by={cfg.eligibility_overridden_by}] "
                     f"{cfg.eligibility_override_note}")
    logger.info("sender-eligibility override recorded for %s (reason=%s, by=%s)",
                sender_instance_id, reason, cfg.eligibility_overridden_by)
    return cfg


async def enforce_for_assignment(db, sender_instance_id: str | None, *,
                                 override: bool = False, note: str | None = None,
                                 by: str = DEFAULT_OVERRIDER,
                                 now: datetime | None = None) -> None:
    """PART 2 gate — called wherever a sender is DESIGNATED for a contact. No-op when the sender is
    eligible (or already validly overridden). When ineligible:
      • with `override=True` + a non-empty note → persist the override + audit log, then allow;
      • otherwise → raise ValueError(<specific Persian reason>) so the API returns 400.
    A None/empty sender is not gated (senderless/global — governed elsewhere)."""
    if not sender_instance_id:
        return
    now = now or datetime.utcnow()
    eligible, reason, msg, _age = await check_sender_eligibility(db, sender_instance_id, now)
    if eligible:
        return
    if override:
        if not (note or "").strip():
            raise ValueError(NOTE_REQUIRED_FA)
        await record_override(db, sender_instance_id, note, by=by, reason=reason, now=now)
        return
    # No override in THIS request, but a prior deliberate override already stands → allow (the
    # sender was consciously approved before; re-confirming on every contact add would be noise).
    if await has_valid_override(db, sender_instance_id):
        return
    raise ValueError(msg or GENERIC_INELIGIBLE_FA)


async def sender_send_allowed(db, sender_instance_id: str | None,
                              now: datetime | None = None) -> tuple[bool, str]:
    """PART 3 send-time defense-in-depth. Returns (allowed, reason_slug). A sender may send only if
    it is currently eligible OR carries a valid logged override. A None sender is allowed (legacy
    senderless contact — the global toggle governs it). reason ∈ {ok, overridden, <ineligible slug>}."""
    if not sender_instance_id:
        return True, "ok"
    now = now or datetime.utcnow()
    eligible, reason, _msg, _age = await check_sender_eligibility(db, sender_instance_id, now)
    if eligible:
        return True, "ok"
    if await has_valid_override(db, sender_instance_id):
        return True, "overridden"
    return False, reason
