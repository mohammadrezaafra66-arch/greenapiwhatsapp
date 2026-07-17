"""V26 PART 4 — voice transcription (Whisper) + detection on the transcript.

Proves (mock OpenAI + a fake ogg, no network/ffmpeg):
  • a pending voice row is downloaded, transcribed, stored 'done', and detection runs on the
    transcript (auto-reply only when the group has it enabled);
  • a download failure marks 'failed' with a reason and never crashes;
  • an oversized (>25MB) file is skipped/flagged 'failed';
  • the ffmpeg fallback path is exercised on a first-call format rejection;
  • idempotent: a 'done' row is not re-transcribed.
"""
import uuid
import pytest
import contextlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services import group_voice as gv
from app.models.group_monitor import (
    GroupMessage, TRANSCRIPTION_DONE, TRANSCRIPTION_FAILED, TRANSCRIPTION_PENDING,
)


# ── pure helpers ─────────────────────────────────────────────────────────────
def test_is_format_rejection():
    assert gv.is_format_rejection(Exception("Invalid file format: could not decode"))
    assert gv.is_format_rejection(Exception("unsupported audio"))
    assert not gv.is_format_rejection(Exception("429 rate limit exceeded"))
    assert not gv.is_format_rejection(Exception("connection timeout"))


@pytest.mark.asyncio
async def test_transcribe_with_fallback_direct_success():
    calls = []
    async def tx(path, key, lang):
        calls.append(path); return "متن فارسی"
    out = await gv.transcribe_with_fallback("a.ogg", "k", "fa", transcribe_fn=tx,
                                            convert_fn=AsyncMock())
    assert out == "متن فارسی" and calls == ["a.ogg"]


@pytest.mark.asyncio
async def test_transcribe_with_fallback_converts_on_format_error():
    seen = []
    async def tx(path, key, lang):
        seen.append(path)
        if path.endswith(".ogg"):
            raise Exception("Invalid file format")   # first call rejects the ogg
        return "متن از mp3"
    async def convert(path):
        return path.replace(".ogg", ".mp3")
    out = await gv.transcribe_with_fallback("v.ogg", "k", "fa",
                                            transcribe_fn=tx, convert_fn=convert)
    assert out == "متن از mp3"
    assert seen == ["v.ogg", "v.mp3"]               # retried exactly once, on the mp3


@pytest.mark.asyncio
async def test_transcribe_non_format_error_raises_voiceerror():
    async def tx(path, key, lang):
        raise Exception("429 rate limit")
    with pytest.raises(gv.VoiceError):
        await gv.transcribe_with_fallback("v.ogg", "k", "fa", transcribe_fn=tx,
                                          convert_fn=AsyncMock())


# ── orchestrator harness ─────────────────────────────────────────────────────
class _DB:
    """Minimal session: get() returns the shared GroupMessage; commit() is a no-op."""
    def __init__(self, gm): self.gm = gm; self.committed = 0
    async def get(self, model, pk): return self.gm
    async def commit(self): self.committed += 1
    def add(self, obj): pass
    async def execute(self, q):
        # Only run_detection_and_reply touches execute; return "no keywords / no group".
        class _R:
            def scalars(self): return SimpleNamespace(all=lambda: [])
            def scalar(self): return 0
            def scalar_one_or_none(self): return None
        return _R()


def _mk_gm(**kw):
    d = dict(listener_instance_id="7105", group_id="g@g.us", group_name="G",
             sender="s@c.us", sender_name="علی", id_message="AUD1",
             type_message="audioMessage", is_voice=True,
             audio_url="https://green/a.ogg", transcription_status=TRANSCRIPTION_PENDING)
    d.update(kw)
    gm = GroupMessage(**d); gm.id = uuid.uuid4()
    return gm


@pytest.fixture
def patch_session(monkeypatch):
    def _apply(gm):
        db = _DB(gm)
        @contextlib.asynccontextmanager
        async def _ctx():
            yield db
        monkeypatch.setattr(gv, "AsyncSessionLocal", lambda: _ctx())
        monkeypatch.setattr(gv, "get_openai_key", AsyncMock(return_value="sk-test"))
        return db
    return _apply


@pytest.mark.asyncio
async def test_pending_voice_transcribed_and_detected(monkeypatch, patch_session):
    gm = _mk_gm()
    db = patch_session(gm)
    detect_mock = AsyncMock()
    monkeypatch.setattr("app.services.group_monitor_engine.run_detection_and_reply", detect_mock)

    async def dl(url, dest): return 12345
    async def tx(path, key, lang): return "قیمت این یخچال چنده"

    res = await gv.process_voice_message(str(gm.id), download_fn=dl, transcribe_fn=tx)
    assert res["status"] == "done"
    assert gm.transcription == "قیمت این یخچال چنده"
    assert gm.transcription_status == TRANSCRIPTION_DONE
    assert gm.audio_local_path and gm.audio_local_path.endswith(".ogg")
    detect_mock.assert_awaited_once()               # detection ran on the transcript


@pytest.mark.asyncio
async def test_download_failure_marks_failed(monkeypatch, patch_session):
    gm = _mk_gm()
    patch_session(gm)
    async def dl(url, dest): raise Exception("404 expired url")
    res = await gv.process_voice_message(str(gm.id), download_fn=dl,
                                         transcribe_fn=AsyncMock())
    assert res["status"] == "failed" and res["reason"] == "download failed"
    assert gm.transcription_status == TRANSCRIPTION_FAILED
    assert "download failed" in gm.transcription_error


@pytest.mark.asyncio
async def test_oversized_file_flagged(monkeypatch, patch_session):
    gm = _mk_gm()
    patch_session(gm)
    async def dl(url, dest): return gv.WHISPER_MAX_BYTES + 1
    res = await gv.process_voice_message(str(gm.id), download_fn=dl,
                                         transcribe_fn=AsyncMock())
    assert res["status"] == "failed" and res["reason"] == "too large"
    assert gm.transcription_status == TRANSCRIPTION_FAILED


@pytest.mark.asyncio
async def test_idempotent_done_row_not_retranscribed(monkeypatch, patch_session):
    gm = _mk_gm(transcription_status=TRANSCRIPTION_DONE, transcription="قبلا انجام شد")
    patch_session(gm)
    tx = AsyncMock()
    res = await gv.process_voice_message(str(gm.id), download_fn=AsyncMock(), transcribe_fn=tx)
    assert res["status"] == "skip" and res["reason"] == "already done"
    tx.assert_not_awaited()                          # never re-transcribed


@pytest.mark.asyncio
async def test_ffmpeg_fallback_exercised_in_pipeline(monkeypatch, patch_session):
    gm = _mk_gm()
    patch_session(gm)
    monkeypatch.setattr("app.services.group_monitor_engine.run_detection_and_reply", AsyncMock())
    async def dl(url, dest): return 500

    order = []
    async def tx(path, key, lang):
        order.append(path)
        if path.endswith(".ogg"):
            raise Exception("Invalid file format")
        return "متن نهایی"
    async def convert(path):
        order.append("convert"); return path.replace(".ogg", ".mp3")

    res = await gv.process_voice_message(str(gm.id), download_fn=dl,
                                         transcribe_fn=tx, convert_fn=convert)
    assert res["status"] == "done" and gm.transcription == "متن نهایی"
    assert "convert" in order and order[-1].endswith(".mp3")


@pytest.mark.asyncio
async def test_retryable_error_raises_and_marks_failed(monkeypatch, patch_session):
    gm = _mk_gm()
    patch_session(gm)
    async def dl(url, dest): return 500
    async def tx(path, key, lang): raise Exception("500 server error")
    with pytest.raises(gv.VoiceError):
        await gv.process_voice_message(str(gm.id), download_fn=dl, transcribe_fn=tx)
    assert gm.transcription_status == TRANSCRIPTION_FAILED
