"""V36 PART 3 one-off: retro-run completion detection against historical inbox_messages.

For every task still stuck at asked/reminded/no_response whose contact ALREADY messaged the
assigned cold account (but was missed by the old phone-format bug), replay that earliest historical
incoming through the normal, now-fixed `handle_helper_incoming` — so the task transitions to `done`
and the (late) thank-you fires through the usual gated/paced path. Per V33, a late completion after
`no_response` is still honored.

Run inside the backend container AFTER the backfill:  python scripts_retro_complete_missed.py
Guardrails: reuses handle_helper_incoming verbatim (same health-gate/pacer as the live webhook);
no polling; touches only warmup_helper_task/thread/log + the normal thank-you send. Idempotent — a
task already `done` is skipped (no open task → the handler no-ops)."""
import asyncio, json
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.warmup_helpers import WarmupHelper, WarmupHelperTask
from app.models.inbox import InboxMessage
from app.services import warmup_helper_service as hs
from app.services import warmup_helper_engine as he

STUCK = ("asked", "reminded", "no_response")


async def main():
    results = []
    async with AsyncSessionLocal() as db:
        tasks = (await db.execute(
            select(WarmupHelperTask).where(WarmupHelperTask.status.in_(STUCK))
        )).scalars().all()
        for t in tasks:
            helper = await db.get(WarmupHelper, t.helper_id)
            if helper is None:
                continue
            forms = list({f for p in (helper.phone, helper.phone_secondary)
                          for f in hs.phone_match_forms(p)})
            if not forms:
                continue
            # earliest genuine incoming from this contact to THIS cold account
            msg = (await db.execute(
                select(InboxMessage).where(
                    InboxMessage.instance_id == t.cold_instance_id,
                    InboxMessage.sender_phone.in_(forms),
                    InboxMessage.is_group.is_(False),
                ).order_by(InboxMessage.received_at.asc()).limit(1)
            )).scalar_one_or_none()
            if msg is None:
                continue
            r = await he.handle_helper_incoming(
                db, t.cold_instance_id, msg.sender_phone, message_text=msg.text_content)
            await db.commit()
            results.append({
                "contact": helper.name, "phone": helper.phone,
                "cold": t.cold_instance_id, "first_msg_at": str(msg.received_at),
                "completed": r is not None,
                "thanked_now": bool(r and r.get("thanked")),
                "thankyou_scheduled": bool(r and r.get("thankyou_scheduled")),
                "thread_paused": bool(r and r.get("thread_paused")),
            })
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
