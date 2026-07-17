"""V26 PART 4 — voice processing: download OGG → OpenAI Whisper (Persian) → reuse detection.

WhatsApp voice notes are OGG/Opus. OpenAI's transcription API accepts OGG directly; if a
call ever rejects the file we convert ogg→mp3 with ffmpeg and retry ONCE. The OpenAI key
comes from the existing AI key pool (falls back to the env key). The whole pipeline runs in
a Celery task so the webhook stays fast; it is idempotent (a 'done' row is never
re-transcribed) and respects Whisper's 25 MB limit (larger notes are flagged, not sent).

Every external seam (download / transcribe / ffmpeg convert) is injectable so the pipeline
unit-tests without the network, OpenAI, or ffmpeg.
"""
from __future__ import annotations
import logging
import os
import tempfile
import uuid

from app.database import AsyncSessionLocal
from app.models.group_monitor import (
    GroupMessage, TRANSCRIPTION_DONE, TRANSCRIPTION_FAILED, TRANSCRIPTION_PENDING,
)

logger = logging.getLogger("afrakala.group_voice")

WHISPER_MAX_BYTES = 25 * 1024 * 1024   # OpenAI Whisper hard limit
_FORMAT_HINTS = ("format", "invalid file", "could not", "decode", "unsupported",
                 "not supported", "corrupt", "ffmpeg")


class VoiceError(Exception):
    """Non-format transcription failure (network/quota) — the task retries with backoff."""


def _voice_dir() -> str:
    d = os.path.join(tempfile.gettempdir(), "afrakala_group_voice")
    os.makedirs(d, exist_ok=True)
    return d


def is_format_rejection(err: Exception) -> bool:
    """True if the error looks like the file format was rejected (→ ffmpeg fallback)."""
    m = str(err).lower()
    return any(h in m for h in _FORMAT_HINTS)


async def get_openai_key() -> str | None:
    """OpenAI key from the AI key pool (preferred) or the env var. None if none configured."""
    try:
        from app.services.ai_key_pool import get_working_key
        k = await get_working_key("openai")
        if k and k.api_key:
            return k.api_key
    except Exception as e:
        logger.debug("ai_key_pool openai lookup failed: %s", e)
    from app.config import settings
    return settings.openai_api_key or None


async def default_download(url: str, dest_path: str) -> int:
    """Download `url` to `dest_path`, returning the byte size. Raises on HTTP error."""
    import httpx
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
        async with c.stream("GET", url) as r:
            r.raise_for_status()
            size = 0
            with open(dest_path, "wb") as f:
                async for chunk in r.aiter_bytes():
                    size += len(chunk)
                    f.write(chunk)
    return size


async def default_transcribe(path: str, api_key: str, language: str = "fa") -> str:
    """Call OpenAI Whisper (whisper-1) to transcribe `path`. Runs the blocking SDK call in a
    thread. Raises on API/format errors (the orchestrator classifies them)."""
    import asyncio

    def _blocking() -> str:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        with open(path, "rb") as fh:
            resp = client.audio.transcriptions.create(
                model="whisper-1", file=fh, language=language)
        return getattr(resp, "text", "") or ""

    return await asyncio.to_thread(_blocking)


async def default_convert(path: str) -> str:
    """Convert an OGG/Opus file to MP3 via ffmpeg; returns the new path. Raises if ffmpeg
    is unavailable or fails (caller treats that as a transcription failure)."""
    import asyncio

    out = os.path.splitext(path)[0] + ".mp3"
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", path, out,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0 or not os.path.exists(out):
        raise VoiceError(f"ffmpeg convert failed: {stderr.decode('utf-8', 'ignore')[:200]}")
    return out


async def transcribe_with_fallback(path: str, api_key: str, language: str = "fa", *,
                                   transcribe_fn=None, convert_fn=None) -> str:
    """Transcribe `path`; on a FORMAT rejection convert ogg→mp3 and retry exactly once.
    Any non-format error propagates (→ task backoff)."""
    transcribe_fn = transcribe_fn or default_transcribe
    convert_fn = convert_fn or default_convert
    try:
        return await transcribe_fn(path, api_key, language)
    except Exception as e:
        if not is_format_rejection(e):
            raise VoiceError(str(e)) from e
        logger.info("Whisper rejected the file format — converting with ffmpeg and retrying once")
        converted = await convert_fn(path)
        return await transcribe_fn(converted, api_key, language)


async def _mark_failed(gm_id: uuid.UUID, reason: str) -> None:
    async with AsyncSessionLocal() as db:
        gm = await db.get(GroupMessage, gm_id)
        if gm:
            gm.transcription_status = TRANSCRIPTION_FAILED
            gm.transcription_error = (reason or "")[:1000]
            await db.commit()


async def process_voice_message(gm_id: str, *, download_fn=None, transcribe_fn=None,
                                convert_fn=None, language: str = "fa") -> dict:
    """Download → transcribe → store → run detection on the transcript. Idempotent (a 'done'
    row is skipped). Returns a small status dict. Raises VoiceError for retryable failures
    (so the Celery task can back off); non-retryable outcomes are marked 'failed' and return.
    """
    download_fn = download_fn or default_download
    gid = uuid.UUID(gm_id)

    # ── load + idempotency guard ─────────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        gm = await db.get(GroupMessage, gid)
        if not gm or not gm.is_voice:
            return {"status": "skip", "reason": "not a voice message"}
        if gm.transcription_status == TRANSCRIPTION_DONE:
            return {"status": "skip", "reason": "already done"}
        audio_url = gm.audio_url

    if not audio_url:
        await _mark_failed(gid, "no audio_url")
        return {"status": "failed", "reason": "no audio_url"}

    # ── download ─────────────────────────────────────────────────────────────
    local_path = os.path.join(_voice_dir(), f"{gid}.ogg")
    try:
        size = await download_fn(audio_url, local_path)
    except Exception as e:
        await _mark_failed(gid, f"download failed: {e}")
        return {"status": "failed", "reason": "download failed"}

    if size is not None and size > WHISPER_MAX_BYTES:
        await _mark_failed(gid, f"audio too large ({size} bytes > 25MB)")
        return {"status": "failed", "reason": "too large"}

    # ── OpenAI key ───────────────────────────────────────────────────────────
    api_key = await get_openai_key()
    if not api_key:
        await _mark_failed(gid, "no OpenAI key available")
        return {"status": "failed", "reason": "no key"}

    # ── transcribe (ffmpeg fallback on format rejection) ─────────────────────
    try:
        text = await transcribe_with_fallback(
            local_path, api_key, language,
            transcribe_fn=transcribe_fn, convert_fn=convert_fn)
    except VoiceError as e:
        # Retryable (network/quota/ffmpeg) — mark failed AND re-raise so the task backs off.
        await _mark_failed(gid, f"transcription error: {e}")
        raise

    text = (text or "").strip()

    # ── store + detect on transcript ─────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        gm = await db.get(GroupMessage, gid)
        if not gm:
            return {"status": "skip", "reason": "message vanished"}
        if gm.transcription_status == TRANSCRIPTION_DONE:
            return {"status": "skip", "reason": "already done (race)"}
        gm.audio_local_path = local_path
        gm.transcription = text
        gm.transcription_status = TRANSCRIPTION_DONE
        await db.commit()

        if text:
            # Reuse the SAME PART 3 detection + auto-reply path on the transcript.
            from app.services.group_monitor_engine import run_detection_and_reply
            gm2 = await db.get(GroupMessage, gid)
            await run_detection_and_reply(db, gm2, text)

    return {"status": "done", "chars": len(text)}
