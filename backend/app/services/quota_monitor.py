"""V27 PART 10 — tariff/quota (466) monitoring and alerting.

When an account's tariff or monthly quota is exceeded, Green API returns 466 and silently
queues messages — the SAME visible symptom as a ban ("nothing is sending") but a completely
different cause (billing, not health). This module detects that condition from either a raised
GreenQuotaExceeded / 466 HTTP error or the quotaExceeded webhook, and records a DISTINCT
Persian admin alert so the user doesn't waste time debugging warm-up/peer/ban logic.
"""
from __future__ import annotations
import logging
from datetime import datetime

logger = logging.getLogger("afrakala.quota_monitor")

QUOTA_STATUS_CODE = 466
QUOTA_INCIDENT_TYPE = "quotaExceeded"   # deliberately NOT "yellowCard"/"blocked"

QUOTA_ALERT_FA = (
    "سهمیه یا تعرفه‌ی حساب محدود شده — این ربطی به بن‌شدن ندارد، لطفاً تعرفه یا سهمیه را در "
    "Green API بررسی کنید."
)


def is_quota_error(exc) -> bool:
    """True if `exc` represents a Green API 466 tariff/quota response (typed exception, an
    httpx 466, or a message mentioning 466/quota)."""
    if exc is None:
        return False
    # typed exception from the Green API client
    try:
        from app.services.green_api import GreenQuotaExceeded
        if isinstance(exc, GreenQuotaExceeded):
            return True
    except Exception:  # pragma: no cover
        pass
    # httpx.HTTPStatusError with a 466 response
    resp = getattr(exc, "response", None)
    if resp is not None and getattr(resp, "status_code", None) == QUOTA_STATUS_CODE:
        return True
    msg = str(exc).lower()
    return "466" in msg or "quote_exceeded" in msg or "quota" in msg and "exceed" in msg


async def record_quota_incident(db, account, via: str = "api",
                                now: datetime | None = None):
    """Mark the account quota-exceeded and record a DISTINCT Persian admin alert incident
    (never a yellowCard/ban). Idempotent per account per day is not required — the incident row
    is cheap and its distinct type keeps it out of ban/health flows. Returns the incident."""
    from app.models.incident import AccountIncident
    now = now or datetime.utcnow()
    account.quota_exceeded_at = now       # existing field — do NOT ban (quota resets)
    incident = AccountIncident(
        account_id=account.id,
        id_instance=int(account.instance_id) if str(account.instance_id).isdigit() else None,
        incident_type=QUOTA_INCIDENT_TYPE, detected_via=via, severity="warning",
        auto_actions={"kind": "tariff_or_quota_limit", "http_status": QUOTA_STATUS_CODE},
        notes=QUOTA_ALERT_FA,
    )
    db.add(incident)
    logger.warning("[quota] instance %s hit tariff/quota (466) via %s — NOT a ban",
                   account.instance_id, via)
    return incident
