"""V14 FEATURE 23 — automatic yellowCard incident response.

All actions here are ZERO-RISK (stopping sends / resting the account can never make a
yellowCard worse) so they run automatically. The dangerous "helpful" actions (reboot,
resume) are NEVER here — they're manual buttons, disabled during cooldown.
"""
import logging
from datetime import datetime, timedelta
from sqlalchemy import select
from app.models.account import Account, AccountStatus
from app.models.campaign import Campaign, CampaignStatus
from app.models.incident import AccountIncident
from app.services.green_api import GreenAPIClient
from app.services import governors

logger = logging.getLogger("afrakala.incident")

PAUSE_REASON = "کارت زرد — ارسال خودکار متوقف شد"
COOLDOWN_DAYS = 3
THROTTLE_DAYS = 7


async def _already_handling(account_id, db) -> bool:
    """Avoid re-processing the same yellowCard on every 2-min poll: if there's an
    unresolved critical incident for this account, it's already been handled."""
    row = (await db.execute(
        select(AccountIncident).where(
            AccountIncident.account_id == account_id,
            AccountIncident.incident_type == "yellowCard",
            AccountIncident.resolved.is_(False),
        ).limit(1)
    )).scalar_one_or_none()
    return row is not None


async def handle_yellow_card(account: Account, via: str, db) -> AccountIncident | None:
    """The full automatic response. Idempotent per unresolved incident."""
    if await _already_handling(account.id, db):
        return None
    now = datetime.utcnow()
    client = GreenAPIClient(account.instance_id, account.api_token)
    auto_actions = {}

    # 1) INSTANT SEND-STOP — pause every running campaign (round-robin means any could use it).
    running = (await db.execute(
        select(Campaign).where(Campaign.status == CampaignStatus.running)
    )).scalars().all()
    paused_ids = []
    for c in running:
        c.status = CampaignStatus.paused
        c.pause_reason = PAUSE_REASON
        paused_ids.append(str(c.id))
    auto_actions["send_stop"] = {"paused_campaigns": len(paused_ids)}

    # 2) SNAPSHOT + CLEAR the send queue (queued msgs would each deepen the card).
    queue_snapshot = []
    try:
        q = await client.show_messages_queue()
        queue_snapshot = q if isinstance(q, list) else []
        await client.clear_messages_queue()
        auto_actions["queue_cleared"] = len(queue_snapshot)
    except Exception as e:
        logger.warning("queue snapshot/clear failed for %s: %s", account.instance_id, e)
        auto_actions["queue_cleared"] = "error"

    # 3) AUTO-THROTTLE 0.5 for 7 days + raise delay to ≥15000ms.
    account.throttle_factor = governors.YELLOW_THROTTLE_FACTOR
    account.throttle_until = now + timedelta(days=THROTTLE_DAYS)
    try:
        await client.set_settings({"delaySendMessagesMilliseconds": governors.DEFAULT_DELAY_MS})
        auto_actions["delay_raised_ms"] = governors.DEFAULT_DELAY_MS
    except Exception as e:
        logger.warning("raise delay failed for %s: %s", account.instance_id, e)
    auto_actions["throttle_factor"] = governors.YELLOW_THROTTLE_FACTOR

    # 4) MANDATORY COOLDOWN — the ONLY thing that actually fixes yellowCard.
    account.cooldown_until = now + timedelta(days=COOLDOWN_DAYS)
    auto_actions["cooldown_until"] = account.cooldown_until.isoformat()

    # 6) LOG + counters (health penalty (7) is applied live in account_health via cooldown).
    account.incident_count_7d = (account.incident_count_7d or 0) + 1
    account.last_incident_at = now
    incident = AccountIncident(
        account_id=account.id,
        id_instance=int(account.instance_id) if str(account.instance_id).isdigit() else None,
        incident_type="yellowCard", detected_via=via, severity="critical",
        auto_actions=auto_actions, campaigns_paused=paused_ids, queue_snapshot=queue_snapshot,
    )
    db.add(incident)
    await db.commit()
    await db.refresh(incident)

    # 5) ALERT via a DIFFERENT healthy account (never the carded one).
    try:
        await _send_emergency_alert(account, len(paused_ids), account.cooldown_until, db)
    except Exception as e:
        logger.warning("emergency alert failed: %s", e)

    logger.warning("yellowCard handled for %s (via %s): paused=%d, queue_cleared=%s",
                   account.instance_id, via, len(paused_ids), auto_actions.get("queue_cleared"))
    return incident


async def _send_emergency_alert(carded: Account, paused_n: int, cooldown_until, db):
    from app.models.reporting import EmergencyContact
    from app.utils.shamsi import to_shamsi
    recipients = (await db.execute(
        select(EmergencyContact).where(EmergencyContact.is_active.is_(True))
    )).scalars().all()
    if not recipients:
        return
    healthy = (await db.execute(
        select(Account).where(Account.status == AccountStatus.active, Account.id != carded.id)
    )).scalars().all()
    healthy = [a for a in healthy if not governors.in_cooldown(a)]
    if not healthy:
        return
    sender = healthy[0]
    client = GreenAPIClient(sender.instance_id, sender.api_token)
    msg = (f"🔴 هشدار: شماره {carded.name} کارت زرد گرفت. ارسال متوقف شد. "
           f"کمپین‌های متوقف‌شده: {paused_n}. دوره خنک‌سازی تا {to_shamsi(cooldown_until)}.")
    for rc in recipients:
        try:
            await client.send_message(rc.phone, msg)
        except Exception:
            continue


async def apply_warning_throttle(account: Account, reason: str, via: str, db,
                                 factor: float = 0.5, days: int = 7) -> AccountIncident:
    """A warning-severity throttle (low reply rate / block spike) — NO cooldown."""
    now = datetime.utcnow()
    account.throttle_factor = factor
    account.throttle_until = now + timedelta(days=days)
    account.last_incident_at = now
    incident = AccountIncident(
        account_id=account.id,
        id_instance=int(account.instance_id) if str(account.instance_id).isdigit() else None,
        incident_type=reason, detected_via=via, severity="warning",
        auto_actions={"throttle_factor": factor, "throttle_days": days},
    )
    db.add(incident)
    await db.commit()
    return incident
