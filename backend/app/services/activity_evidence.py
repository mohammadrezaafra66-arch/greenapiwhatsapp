"""V67.1 Phase 1 — Real-activity evidence (ZERO DDL).

Computes first/last inbound/outbound and chat diversity from existing tables.
Does NOT use calendar age or connected_at as maturity proof.
Does NOT fabricate historical backfill — unknown remains None.

Real outbound definition (Phase 1):
- CampaignContact with sent_at set AND green_api_message_id present (accepted idMessage)
- WarmupHelperLog with delivery_ok is True AND id_message present
- WarmupEventLog event_type=send AND delivery_status indicating success with payload id when present
Failed / gated / queued-only sends are excluded.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any

from sqlalchemy import select, func, and_

from app.services.send_metrics import tehran_today_start_utc, real_sent_today, real_sent_today_by_account


async def activity_evidence_for_instance(db, instance_id: str,
                                         now_utc: datetime | None = None) -> dict[str, Any]:
    """Read-only evidence bundle for one instance. No schema writes."""
    now_utc = now_utc or datetime.utcnow()
    from app.models.account import Account
    from app.models.inbox import InboxMessage
    from app.models.campaign import CampaignContact
    from app.models.warmup_helpers import WarmupHelperLog
    from app.models.warmup_mesh import WarmupEventLog, WarmupEnrollment

    acc = (await db.execute(
        select(Account).where(Account.instance_id == instance_id)
    )).scalar_one_or_none()
    account_id = acc.id if acc else None

    # Inbound: inbox_messages for this instance (non-group preferred for unique chats)
    inbound_q = await db.execute(
        select(
            func.min(InboxMessage.received_at),
            func.max(InboxMessage.received_at),
            func.count(),
        ).where(InboxMessage.instance_id == instance_id)
    )
    first_in, last_in, inbound_count = inbound_q.one()
    unique_in = (await db.execute(
        select(func.count(func.distinct(InboxMessage.sender_phone)))
        .where(InboxMessage.instance_id == instance_id,
               InboxMessage.is_group.is_(False),
               InboxMessage.sender_phone.isnot(None))
    )).scalar() or 0

    # Real outbound — campaign
    first_out = last_out = None
    outbound_count = 0
    unique_out_phones: set[str] = set()
    if account_id is not None:
        camp_rows = (await db.execute(
            select(CampaignContact.sent_at, CampaignContact.phone,
                   CampaignContact.green_api_message_id, CampaignContact.delivery_status)
            .where(
                CampaignContact.account_id == account_id,
                CampaignContact.sent_at.isnot(None),
                CampaignContact.green_api_message_id.isnot(None),
                CampaignContact.green_api_message_id != "",
            )
        )).all()
        for sent_at, phone, mid, _st in camp_rows:
            if not mid:
                continue
            outbound_count += 1
            if phone:
                unique_out_phones.add(str(phone))
            if sent_at and (first_out is None or sent_at < first_out):
                first_out = sent_at
            if sent_at and (last_out is None or sent_at > last_out):
                last_out = sent_at

    # Real outbound — team collab (delivery_ok + id_message)
    tc_rows = (await db.execute(
        select(WarmupHelperLog.created_at, WarmupHelperLog.to_phone)
        .where(
            WarmupHelperLog.from_instance_id == instance_id,
            WarmupHelperLog.delivery_ok.is_(True),
            WarmupHelperLog.id_message.isnot(None),
            WarmupHelperLog.id_message != "",
        )
    )).all()
    for created_at, phone in tc_rows:
        outbound_count += 1
        if phone:
            unique_out_phones.add(str(phone))
        if created_at and (first_out is None or created_at < first_out):
            first_out = created_at
        if created_at and (last_out is None or created_at > last_out):
            last_out = created_at

    # Mesh sends with message_id in payload or delivery_status requested/sent/delivered
    enr = (await db.execute(
        select(WarmupEnrollment).where(WarmupEnrollment.instance_id == instance_id)
    )).scalar_one_or_none()
    if enr is not None:
        mesh_rows = (await db.execute(
            select(WarmupEventLog.created_at, WarmupEventLog.delivery_status,
                   WarmupEventLog.payload_json)
            .where(
                WarmupEventLog.enrollment_id == enr.id,
                WarmupEventLog.event_type == "send",
            )
        )).all()
        for created_at, delivery_status, payload_json in mesh_rows:
            # Real = accepted API path: delivery_status not failed/gate_skip; prefer idMessage in payload
            st = (delivery_status or "").lower()
            if st in ("failed", "gate_skip", "skipped"):
                continue
            has_id = False
            if payload_json and "idMessage" in (payload_json or ""):
                has_id = True
            # Phase 1: count mesh send only when delivery_status is requested/sent/delivered/read
            # or payload carries idMessage. "requested" means API returned idMessage in engine.
            if st in ("requested", "sent", "delivered", "read") or has_id:
                outbound_count += 1
                if created_at and (first_out is None or created_at < first_out):
                    first_out = created_at
                if created_at and (last_out is None or created_at > last_out):
                    last_out = created_at

    # Bidirectional: phones that appear in both inbound inbox and outbound sets
    inbound_phones = set(
        (await db.execute(
            select(InboxMessage.sender_phone)
            .where(InboxMessage.instance_id == instance_id,
                   InboxMessage.is_group.is_(False),
                   InboxMessage.sender_phone.isnot(None))
        )).scalars().all()
    )
    bidirectional = len(inbound_phones & unique_out_phones) if inbound_phones and unique_out_phones else 0

    start = tehran_today_start_utc(now_utc)
    # Today counts via existing send_metrics for outbound; inbound from inbox today
    received_today = (await db.execute(
        select(func.count()).select_from(InboxMessage)
        .where(InboxMessage.instance_id == instance_id,
               InboxMessage.received_at >= start)
    )).scalar() or 0

    per = await real_sent_today_by_account(db, now_utc)
    sent_today = int((per.get(instance_id) or {}).get("total") or 0)

    return {
        "instance_id": instance_id,
        "first_real_inbound": first_in.isoformat() if first_in else None,
        "last_real_inbound": last_in.isoformat() if last_in else None,
        "first_real_outbound": first_out.isoformat() if first_out else None,
        "last_real_outbound": last_out.isoformat() if last_out else None,
        "real_sent_today": sent_today,
        "real_received_today": int(received_today),
        "unique_inbound_chats": int(unique_in),
        "unique_outbound_chats": len(unique_out_phones),
        "bidirectional_chats": int(bidirectional),
        "inbound_message_count": int(inbound_count or 0),
        "real_outbound_count": int(outbound_count),
        "maturity_note": "connected_at/calendar_age are NOT used as maturity proof",
        "schema": "existing_tables_only_zero_ddl",
    }


# Pure helpers for unit tests (no DB)
def is_real_outbound_campaign(green_api_message_id, sent_at, delivery_status=None) -> bool:
    if not sent_at:
        return False
    if not green_api_message_id:
        return False
    st = (delivery_status or "").lower()
    if st == "failed":
        return False  # failed after accept still had idMessage — Phase 1 counts accept;
    # Acceptance with idMessage counts as real outbound; delivery tracked separately.
    return True


def is_real_outbound_helper(delivery_ok, id_message) -> bool:
    return bool(delivery_ok) and bool(id_message)
