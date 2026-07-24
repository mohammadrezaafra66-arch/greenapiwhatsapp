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
    # V14 F23.3.7 — an account resting in cooldown scores 0 so smart rotation routes
    # around it automatically.
    from app.services.governors import in_cooldown
    if in_cooldown(account):
        return 0.0
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


async def protection_snapshot(account, db) -> dict:
    """V48 — the EXACT per-account row the «محافظت و سلامت» page (`/incidents/protection`)
    builds, extracted so the unified accounts overview reuses it verbatim (no drift).
    Combines `health_breakdown` with the cooldown/throttle governors and the trailing-7d
    reply rate. Output is byte-identical to what the protection endpoint returned inline."""
    from app.services import governors
    from app.models.account import AccountStatus
    from app.utils.shamsi import to_shamsi
    hb = await health_breakdown(account, db)
    cutoff = datetime.utcnow() - timedelta(days=WINDOW_DAYS)
    total = (await db.execute(select(func.count()).select_from(CampaignContact).where(
        CampaignContact.account_id == account.id, CampaignContact.sent_at >= cutoff))).scalar() or 0
    replied = (await db.execute(select(func.count()).select_from(CampaignContact).where(
        CampaignContact.account_id == account.id, CampaignContact.sent_at >= cutoff,
        CampaignContact.replied.is_(True)))).scalar() or 0
    reply_rate = round(replied / total, 3) if total else None
    cd = governors.in_cooldown(account)
    status_val = account.status.value if hasattr(account.status, "value") else account.status
    green_api_deleted = status_val == AccountStatus.green_api_deleted.value
    return {
        "account_id": str(account.id),
        "name": account.name,
        "status": status_val,
        "green_api_deleted": green_api_deleted,
        "green_api_deleted_message": "این اینستنس در Green API دیگر وجود ندارد" if green_api_deleted else None,
        "health_score": 0.0 if cd else hb["score"],
        "sent_today": hb["sent_today"],
        "effective_cap": governors.effective_daily_cap(account),
        "yellow_card_rate_7d": hb["yellow_card_rate"],
        "reply_rate_7d": reply_rate,
        "throttle_factor": account.throttle_factor or 1.0,
        "throttle_until": to_shamsi(account.throttle_until),
        "in_cooldown": cd,
        "cooldown_until": to_shamsi(account.cooldown_until),
        "incident_count_7d": account.incident_count_7d or 0,
    }


def pick_account_weighted(accounts, scores):
    """Weighted-random account choice by health score. Falls back to a neutral 0.5
    for any account without a score, and to a plain choice if all weights are ~0."""
    if not accounts:
        return None
    weights = [max(0.01, float(scores.get(str(a.id), 0.5))) for a in accounts]
    return random.choices(accounts, weights=weights, k=1)[0]
