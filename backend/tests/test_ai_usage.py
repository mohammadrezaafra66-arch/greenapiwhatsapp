"""Tests for AI token-usage extraction + logging (dashboard bug #2).

The production 0-token rows were all FAILED calls (429/401) — the extraction
logic itself is correct. These tests prove that on a *successful* response the
prompt/completion/total tokens are parsed from response.usage and logged.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _fake_httpx_client(json_payload):
    """Build a MagicMock standing in for httpx.AsyncClient() as an async CM."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=json_payload)
    client = MagicMock()
    client.post = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


@pytest.mark.asyncio
async def test_openai_call_extracts_usage_tokens():
    from app.services import gpt_service
    payload = {
        "choices": [{"message": {"content": "سلام دوست عزیز"}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
    }
    with patch.object(gpt_service.httpx, "AsyncClient", return_value=_fake_httpx_client(payload)):
        text, pt, ct, tt = await gpt_service._call_openai_compatible(
            "http://x", "key", "gpt-4o-mini", "sys", "usr", 100, 0.5
        )
    assert text == "سلام دوست عزیز"
    assert (pt, ct, tt) == (12, 8, 20)


@pytest.mark.asyncio
async def test_openai_call_derives_total_when_missing():
    from app.services import gpt_service
    # usage without total_tokens → total is derived as prompt + completion
    payload = {
        "choices": [{"message": {"content": "x"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 7},
    }
    with patch.object(gpt_service.httpx, "AsyncClient", return_value=_fake_httpx_client(payload)):
        _text, pt, ct, tt = await gpt_service._call_openai_compatible(
            "http://x", "key", "gpt-4o-mini", "sys", "usr", 100, 0.5
        )
    assert (pt, ct, tt) == (5, 7, 12)


@pytest.mark.asyncio
async def test_chat_logs_usage_tokens_on_success():
    from app.services import gpt_service
    log_mock = AsyncMock()
    with patch.object(gpt_service, "PROVIDERS", [{"name": "openai", "model": "gpt-4o-mini", "base": "http://x"}]), \
         patch.object(gpt_service, "_key_for", return_value="key"), \
         patch.object(gpt_service, "_call_openai_compatible", new=AsyncMock(return_value=("متن", 12, 8, 20))), \
         patch.object(gpt_service, "_log_usage", new=log_mock):
        out = await gpt_service._chat("sys", "usr", 100, 0.5)
    assert out == "متن"
    log_mock.assert_awaited_once()
    # _log_usage(provider, model, pt, ct, tt, success, error_text)
    args = log_mock.await_args.args
    assert args[2] == 12 and args[3] == 8 and args[4] == 20
    assert args[5] is True


@pytest.mark.asyncio
async def test_chat_logs_zero_tokens_on_failure():
    from app.services import gpt_service
    log_mock = AsyncMock()
    with patch.object(gpt_service, "PROVIDERS", [{"name": "openai", "model": "gpt-4o-mini", "base": "http://x"}]), \
         patch.object(gpt_service, "_key_for", return_value="key"), \
         patch.object(gpt_service, "_call_openai_compatible", new=AsyncMock(side_effect=Exception("429 Too Many Requests"))), \
         patch.object(gpt_service, "_log_usage", new=log_mock):
        out = await gpt_service._chat("sys", "usr", 100, 0.5)
    assert out is None  # no provider succeeded
    # failure is logged with zero tokens + success=False (this is why prod rows are 0)
    args = log_mock.await_args.args
    assert args[2] == 0 and args[3] == 0 and args[4] == 0
    assert args[5] is False
