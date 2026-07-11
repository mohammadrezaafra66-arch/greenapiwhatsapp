"""Ensure Green API errors surfaced to clients never leak the instance URL/token."""
import httpx
from app.api.v1.groups import _green_error

TOKEN = "b9ebd1a4e3a04d8c971294ef3af4445d9922df1913454c3e8d"
URL = f"https://api.green-api.com/waInstance09122270261/getChats/{TOKEN}"


def _status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", URL)
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError(f"Client error '{code}' for url '{URL}'", request=request, response=response)


def test_403_returns_friendly_message_without_token():
    msg = _green_error(_status_error(403))
    assert TOKEN not in msg
    assert "green-api.com" not in msg
    assert "403" in msg


def test_other_status_code_without_token():
    msg = _green_error(_status_error(502))
    assert TOKEN not in msg
    assert "502" in msg


def test_non_http_exception_is_truncated():
    msg = _green_error(RuntimeError("boom " * 100))
    assert len(msg) <= 200
