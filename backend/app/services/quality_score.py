"""V27 PART 8 — live per-instance quality score (reply-rate + failure-rate auto-throttle).

WhatsApp's trust assessment reportedly weighs engagement (opens/replies), not just volume.
This applies CONTINUOUSLY to any campaign-sending instance (GRADUATED or otherwise), not only
numbers formally inside a warm-up enrollment — reusing the same reply-rate ("نسبت پاسخ")
plumbing already built for the mesh.

A rolling score blends recent reply rate and recent failed-delivery rate. Below a conservative
threshold the instance's OUTBOUND campaign sending is auto-throttled and a Persian notice is
surfaced on the dashboard (as a warning incident). Thresholds are documented constants — a cold
sales campaign has a naturally lower reply rate than person-to-person chat, so the reply target
is modest and the (more reliable) delivery signal is weighted higher.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, func

from app.models.campaign import CampaignContact
from app.models.incident import AccountIncident

logger = logging.getLogger("afrakala.quality_score")

QUALITY_WINDOW_DAYS = 7
MIN_SAMPLE = 20                 # need >= this many recent sends before judging
# "~40% reply rate is good" (research) — but a cold campaign is far lower, so normalise the
# reply component against this modest target and weight the delivery signal higher.
GOOD_REPLY_RATE = 0.40
REPLY_WEIGHT = 0.4
DELIVERY_WEIGHT = 0.6
# Below this 0..1 score → auto-throttle. Conservative + easy to tune.
QUALITY_THRESHOLD = 0.5
THROTTLE_FACTOR = 0.5
THROTTLE_DAYS = 3

LOW_QUALITY_FA = "کیفیت این اکانت افت کرده — ارسال آن به‌صورت خودکار کند/متوقف شد."


def compute_quality_score(reply_rate: float, failure_rate: float) -> float:
    """Pure 0..1 quality score. Higher = healthier engagement + delivery."""
    reply_component = min(1.0, max(0.0, reply_rate) / GOOD_REPLY_RATE) if GOOD_REPLY_RATE else 0.0
    delivery_component = 1.0 - min(1.0, max(0.0, failure_rate))
    score = REPLY_WEIGHT * reply_component + DELIVERY_WEIGHT * delivery_component
    return max(0.0, min(1.0, score))


def is_low_quality(score: float, threshold: float = QUALITY_THRESHOLD) -> bool:
    return score < threshold


async def instance_quality(db, account, now: datetime | None = None,
                           window_days: int = QUALITY_WINDOW_DAYS) -> dict:
    """Rolling reply-rate + failure-rate + blended score for one instance. When too few recent
    sends exist to judge, score is None (never throttled on noise)."""
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=window_days)
    total = (await db.execute(
        select(func.count()).select_from(CampaignContact).where(
            CampaignContact.account_id == account.id, CampaignContact.sent_at >= cutoff)
    )).scalar() or 0
    if total < MIN_SAMPLE:
        return {"score": None, "sample": total, "reply_rate": None, "failure_rate": None,
                "reason": "insufficient_sample"}
    replied = (await db.execute(
        select(func.count()).select_from(CampaignContact).where(
            CampaignContact.account_id == account.id, CampaignContact.sent_at >= cutoff,
            CampaignContact.replied.is_(True))
    )).scalar() or 0
    failed = (await db.execute(
        select(func.count()).select_from(CampaignContact).where(
            CampaignContact.account_id == account.id, CampaignContact.sent_at >= cutoff,
            CampaignContact.delivery_status == "failed")
    )).scalar() or 0
    reply_rate = replied / total
    failure_rate = failed / total
    return {"score": compute_quality_score(reply_rate, failure_rate), "sample": total,
            "reply_rate": reply_rate, "failure_rate": failure_rate, "reason": None}


async def evaluate_and_act(db, account, now: datetime | None = None) -> dict:
    """Compute the score and, if low, auto-throttle the instance's outbound campaign sending
    and record a Persian warning incident for the dashboard. Idempotent-ish: skips if the
    instance is already throttled. Returns the evaluation + what was done."""
    from app.services import governors
    now = now or datetime.utcnow()
    q = await instance_quality(db, account, now)
    q["acted"] = None
    q["notice"] = None
    if q["score"] is None or not is_low_quality(q["score"]):
        return q
    if governors.is_throttled(account, now):
        q["acted"] = "already_throttled"
        return q
    # Throttle outbound sending (mirrors incident_handler.apply_warning_throttle semantics).
    account.throttle_factor = THROTTLE_FACTOR
    account.throttle_until = now + timedelta(days=THROTTLE_DAYS)
    account.last_incident_at = now
    db.add(AccountIncident(
        account_id=account.id,
        id_instance=int(account.instance_id) if str(account.instance_id).isdigit() else None,
        incident_type="lowQualityScore", detected_via="quality_monitor", severity="warning",
        auto_actions={"throttle_factor": THROTTLE_FACTOR, "throttle_days": THROTTLE_DAYS,
                      "score": round(q["score"], 3), "reply_rate": round(q["reply_rate"], 3),
                      "failure_rate": round(q["failure_rate"], 3)},
        notes=LOW_QUALITY_FA,
    ))
    q["acted"] = "throttled"
    q["notice"] = LOW_QUALITY_FA
    logger.warning("quality auto-throttle %s: score=%.2f reply=%.2f fail=%.2f",
                   account.instance_id, q["score"], q["reply_rate"], q["failure_rate"])
    return q
