"""V13.2 — per-account health scoring for smart send rotation.

Health blends remaining daily capacity (more is better) with the recent yellowCard
rate (lower is better). Healthier accounts get proportionally more sends."""
import random
from datetime import datetime, timedelta
from sqlalchemy import select, func
from app.models.campaign import CampaignContact

CAP_WEIGHT = 0.6
YELLOW_WEIGHT = 0.4
WINDOW_DAYS = 7


async def _stats(account, db):
    """Return (cap_ratio, total_7d, yellow_7d, yellow_rate) for an account."""
    limit = account.computed_daily_limit or 1
    remaining = max(0, limit - (account.sent_today or 0))
    cap_ratio = (remaining / limit) if limit else 0.0
    cutoff = datetime.utcnow() - timedelta(days=WINDOW_DAYS)
    total = (await db.execute(
        select(func.count()).select_from(CampaignContact).where(
            CampaignContact.account_id == account.id,
            CampaignContact.sent_at >= cutoff,
        ))).scalar() or 0
    yellow = (await db.execute(
        select(func.count()).select_from(CampaignContact).where(
            CampaignContact.account_id == account.id,
            CampaignContact.sent_at >= cutoff,
            CampaignContact.delivery_status == "yellowCard",
        ))).scalar() or 0
    yellow_rate = (yellow / total) if total else 0.0
    return cap_ratio, total, yellow, yellow_rate


def compute_score(cap_ratio: float, yellow_rate: float) -> float:
    """Pure 0..1 health score. Higher = healthier/preferred for sending."""
    health = (CAP_WEIGHT * cap_ratio) + (YELLOW_WEIGHT * (1 - yellow_rate))
    return max(0.0, min(1.0, health))


async def account_health_score(account, db) -> float:
    cap_ratio, _total, _yellow, yellow_rate = await _stats(account, db)
    return compute_score(cap_ratio, yellow_rate)


async def health_breakdown(account, db) -> dict:
    cap_ratio, total, yellow, yellow_rate = await _stats(account, db)
    return {
        "score": round(compute_score(cap_ratio, yellow_rate), 3),
        "daily_limit": account.computed_daily_limit or 1,
        "sent_today": account.sent_today or 0,
        "remaining_capacity": max(0, (account.computed_daily_limit or 1) - (account.sent_today or 0)),
        "capacity_ratio": round(cap_ratio, 3),
        "sends_7d": total,
        "yellow_card_7d": yellow,
        "yellow_card_rate": round(yellow_rate, 3),
    }


def pick_account_weighted(accounts, scores):
    """Weighted-random account choice by health score. Falls back to a neutral 0.5
    for any account without a score, and to a plain choice if all weights are ~0."""
    if not accounts:
        return None
    weights = [max(0.01, float(scores.get(str(a.id), 0.5))) for a in accounts]
    return random.choices(accounts, weights=weights, k=1)[0]
