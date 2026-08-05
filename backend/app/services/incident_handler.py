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


async def record_suspension(account: Account, via: str, db) -> AccountIncident | None:
    """V65 — write a Green API spam suspension into the incident table.

    Until now a suspension changed `accounts.status` and `suspended_until` but wrote NO incident
    row. Everything that judges an account's health counts incident ROWS, so a suspended number
    kept reporting perfectly healthy: on 2026-08-03 instance 770022683838 was suspended for
    seven days and still showed warmth 80 «بالا» with incident_count_7d = 0 — meaning it stayed
    eligible to be picked for the next campaign.

    Idempotent per suspension window: re-polling a still-suspended instance every 60s must not
    add a row each time. A NEW suspension after the previous one was resolved does record again.

    `cooldown_until` is deliberately NOT set here. The suspension itself already blocks sending
    through the gate (`suspended` is in BLOCKING_LIVE_STATES and status != active), and inventing
    an extra cooldown would outlive the restriction and silently sideline a recovered number.
    """
    existing = (await db.execute(
        select(AccountIncident).where(
            AccountIncident.account_id == account.id,
            AccountIncident.incident_type == "suspended",
            AccountIncident.resolved.is_(False),
        ).limit(1)
    )).scalar_one_or_none()
    if existing is not None:
        return None

    now = datetime.utcnow()
    account.incident_count_7d = (account.incident_count_7d or 0) + 1
    account.last_incident_at = now
    incident = AccountIncident(
        account_id=account.id,
        id_instance=int(account.instance_id) if str(account.instance_id).isdigit() else None,
        incident_type="suspended", detected_via=via, severity="critical",
        auto_actions={
            "status": "suspended",
            "suspended_until": (account.suspended_until.isoformat()
                                if getattr(account, "suspended_until", None) else None),
            "sent_today_at_suspension": account.sent_today,
        },
        notes="Green API spam restriction (stateInstance=suspended)",
    )
    db.add(incident)
    logger.warning("suspension recorded for %s (via %s), until %s",
                   account.instance_id, via, getattr(account, "suspended_until", None))
    # V67.1 Phase 1 — feed fleet 24h suspension breaker (coexists with mesh 48h; D-C1).
    try:
        from app.services import fleet_breaker
        await fleet_breaker.record_distinct_suspension(str(account.id), via=via)
    except Exception as e:
        logger.error("fleet breaker notify after suspension failed: %s", e)
    return incident


async def resolve_suspension(account: Account, db) -> int:
    """V65 — close open suspension incidents once the instance is authorized again, so a number
    that genuinely recovered is not penalised forever."""
    rows = (await db.execute(
        select(AccountIncident).where(
            AccountIncident.account_id == account.id,
            AccountIncident.incident_type == "suspended",
            AccountIncident.resolved.is_(False),
        )
    )).scalars().all()
    for r in rows:
        r.resolved = True
        r.resolved_at = datetime.utcnow()
        r.resolved_by = "auto"
    return len(rows)


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


# ── V67.1 Phase 1 — critical incident completeness (idempotent) ─────────────

CRITICAL_INCIDENT_TYPES = (
    "yellowCard", "suspended", "blocked", "notAuthorized", "forced_logout",
    "device_restriction", "auth_churn",
)


async def _open_incident(account_id, incident_type: str, db) -> AccountIncident | None:
    return (await db.execute(
        select(AccountIncident).where(
            AccountIncident.account_id == account_id,
            AccountIncident.incident_type == incident_type,
            AccountIncident.resolved.is_(False),
        ).limit(1)
    )).scalar_one_or_none()


def _safe_instance_int(instance_id) -> int | None:
    try:
        return int(instance_id) if str(instance_id).isdigit() else None
    except Exception:
        return None


def _bump_incident_counters(account: Account, now: datetime) -> None:
    account.incident_count_7d = (account.incident_count_7d or 0) + 1
    account.last_incident_at = now


async def record_blocked(account: Account, via: str, db, *, raw_state: str = "blocked",
                         notes: str | None = None) -> AccountIncident | None:
    """V67 Phase 1 — idempotent blocked incident. Does not call Green API / clear queues."""
    if await _open_incident(account.id, "blocked", db) is not None:
        return None
    now = datetime.utcnow()
    _bump_incident_counters(account, now)
    incident = AccountIncident(
        account_id=account.id,
        id_instance=_safe_instance_int(account.instance_id),
        incident_type="blocked", detected_via=via, severity="critical",
        auto_actions={"status": "banned", "raw_state": raw_state},
        notes=notes or "WhatsApp blocked (stateInstance=blocked)",
    )
    db.add(incident)
    logger.warning("blocked recorded for %s (via %s)", account.instance_id, via)
    return incident


async def record_forced_logout(account: Account, via: str, db, *, raw_state: str = "notAuthorized",
                               notes: str | None = None) -> AccountIncident | None:
    """V67 Phase 1 — forced logout / unexpected authorization loss. Idempotent open row."""
    if await _open_incident(account.id, "forced_logout", db) is not None:
        return None
    now = datetime.utcnow()
    _bump_incident_counters(account, now)
    incident = AccountIncident(
        account_id=account.id,
        id_instance=_safe_instance_int(account.instance_id),
        incident_type="forced_logout", detected_via=via, severity="critical",
        auto_actions={"status": "disconnected", "raw_state": raw_state},
        notes=notes or "Forced logout / unexpected authorization loss",
    )
    db.add(incident)
    logger.warning("forced_logout recorded for %s (via %s)", account.instance_id, via)
    return incident


async def record_not_authorized(account: Account, via: str, db, *, raw_state: str = "notAuthorized",
                                unexpected: bool = True) -> AccountIncident | None:
    """Unexpected notAuthorized while the account was previously active/connected."""
    if await _open_incident(account.id, "notAuthorized", db) is not None:
        return None
    now = datetime.utcnow()
    _bump_incident_counters(account, now)
    incident = AccountIncident(
        account_id=account.id,
        id_instance=_safe_instance_int(account.instance_id),
        incident_type="notAuthorized", detected_via=via, severity="critical",
        auto_actions={"unexpected": unexpected, "raw_state": raw_state},
        notes="Unexpected notAuthorized (authorization loss)",
    )
    db.add(incident)
    logger.warning("notAuthorized recorded for %s (via %s)", account.instance_id, via)
    return incident


async def record_device_restriction(account: Account, via: str, db, *,
                                    raw_payload: dict | None = None) -> AccountIncident | None:
    """Linked-device restriction when detectable from device webhook payload."""
    if await _open_incident(account.id, "device_restriction", db) is not None:
        return None
    now = datetime.utcnow()
    _bump_incident_counters(account, now)
    # Never store secrets; only non-sensitive device status fields.
    safe = {}
    if isinstance(raw_payload, dict):
        for k in ("state", "status", "deviceStatus", "reason", "typeWebhook"):
            if k in raw_payload:
                safe[k] = raw_payload.get(k)
    incident = AccountIncident(
        account_id=account.id,
        id_instance=_safe_instance_int(account.instance_id),
        incident_type="device_restriction", detected_via=via, severity="critical",
        auto_actions={"raw_state": safe},
        notes="Linked-device restriction detected",
    )
    db.add(incident)
    logger.warning("device_restriction recorded for %s (via %s)", account.instance_id, via)
    return incident


async def record_auth_churn(account: Account, via: str, db, *,
                            window_hours: int = 24, threshold: int = 3) -> AccountIncident | None:
    """Repeated authorization churn: multiple forced_logout/notAuthorized in a window.

    Only invents this signal when supported by counting prior critical auth incidents.
    """
    cutoff = datetime.utcnow() - timedelta(hours=window_hours)
    n = (await db.execute(
        select(AccountIncident).where(
            AccountIncident.account_id == account.id,
            AccountIncident.incident_type.in_(("forced_logout", "notAuthorized")),
            AccountIncident.created_at >= cutoff,
        )
    )).scalars().all()
    if len(n) < threshold:
        return None
    if await _open_incident(account.id, "auth_churn", db) is not None:
        return None
    now = datetime.utcnow()
    _bump_incident_counters(account, now)
    incident = AccountIncident(
        account_id=account.id,
        id_instance=_safe_instance_int(account.instance_id),
        incident_type="auth_churn", detected_via=via, severity="critical",
        auto_actions={"count_in_window": len(n), "window_hours": window_hours},
        notes="Repeated authorization churn",
    )
    db.add(incident)
    return incident


async def resolve_incident_type(account: Account, incident_type: str, db,
                                resolved_by: str = "auto") -> int:
    rows = (await db.execute(
        select(AccountIncident).where(
            AccountIncident.account_id == account.id,
            AccountIncident.incident_type == incident_type,
            AccountIncident.resolved.is_(False),
        )
    )).scalars().all()
    for r in rows:
        r.resolved = True
        r.resolved_at = datetime.utcnow()
        r.resolved_by = resolved_by
    return len(rows)


async def has_unresolved_critical(account_id, db) -> bool:
    row = (await db.execute(
        select(AccountIncident).where(
            AccountIncident.account_id == account_id,
            AccountIncident.incident_type.in_(CRITICAL_INCIDENT_TYPES),
            AccountIncident.resolved.is_(False),
            AccountIncident.severity == "critical",
        ).limit(1)
    )).scalar_one_or_none()
    return row is not None
