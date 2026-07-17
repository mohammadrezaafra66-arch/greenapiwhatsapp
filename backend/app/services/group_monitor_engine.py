"""V26 — orchestration for a newly-captured group message.

Single stable entry point called by the webhook after ingest:
  • PART 2: (this file) exists so the webhook has one call site; ingest-only.
  • PART 3: text messages run keyword detection + optional auto-reply here.
  • PART 4: voice messages are enqueued for transcription, then detected on the transcript.

Kept fully guarded so it can never disrupt the webhook loop.
"""
from __future__ import annotations
import logging

logger = logging.getLogger("afrakala.group_monitor")


async def handle_new_group_message(gm_id: str) -> None:
    """Dispatch a freshly-ingested group_message. Filled in by PART 3 (detection/auto-reply)
    and PART 4 (voice transcription). No-op-safe for PART 2 (ingest only)."""
    return None
