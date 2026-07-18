"""V27 PART 10 — tariff/quota (466) monitoring and alerting.

Proves:
  • a 466 response is detected as a quota error (typed exc, httpx 466, or message);
  • a ban/yellowCard error is NOT mistaken for a quota error;
  • record_quota_incident produces a DISTINCT Persian alert incident (type quotaExceeded,
    not yellowCard/blocked) and sets quota_exceeded_at without banning;
  • the Green API client raises GreenQuotaExceeded on a 466 response.
"""
import uuid
from datetime import datetime
from types import SimpleNamespace
import httpx
import pytest

from app.services import quota_monitor as qm
from app.services.quota_monitor import (
    is_quota_error, record_quota_incident, QUOTA_ALERT_FA, QUOTA_INCIDENT_TYPE,
)
from app.services.green_api import GreenQuotaExceeded, QUOTA_STATUS_CODE

NOW = datetime(2026, 7, 18, 12, 0, 0)


def _http_error(code):
    req = httpx.Request("POST", "https://api.green-api.com/x")
    return httpx.HTTPStatusError("err", request=req, response=httpx.Response(code, request=req))


# ── detection ────────────────────────────────────────────────────────────────
def test_typed_quota_exception_detected():
    assert is_quota_error(GreenQuotaExceeded("466 limit")) is True


def test_http_466_detected():
    assert is_quota_error(_http_error(466)) is True


def test_message_mentioning_466_detected():
    assert is_quota_error(RuntimeError("Green API tariff/quota limit (466)")) is True


def test_ban_error_not_mistaken_for_quota():
    assert is_quota_error(_http_error(403)) is False
    assert is_quota_error(RuntimeError("yellowCard")) is False
    assert is_quota_error(RuntimeError("blocked by WhatsApp")) is False
    assert is_quota_error(None) is False


# ── distinct incident ────────────────────────────────────────────────────────
class _DB:
    def __init__(self): self.added = []
    def add(self, x): self.added.append(x)


@pytest.mark.asyncio
async def test_record_quota_incident_is_distinct_and_not_a_ban():
    from app.models.incident import AccountIncident
    from app.models.account import AccountStatus
    acc = SimpleNamespace(id=uuid.uuid4(), instance_id="770022680000",
                          status=AccountStatus.active, quota_exceeded_at=None, banned_at=None)
    db = _DB()
    inc = await record_quota_incident(db, acc, via="webhook", now=NOW)
    assert isinstance(inc, AccountIncident)
    assert inc.incident_type == QUOTA_INCIDENT_TYPE == "quotaExceeded"
    assert inc.incident_type not in ("yellowCard", "blocked")   # NOT confused with a ban
    assert inc.notes == QUOTA_ALERT_FA
    assert acc.quota_exceeded_at == NOW
    assert acc.status == AccountStatus.active and acc.banned_at is None   # never banned


# ── client raises the typed error on 466 ─────────────────────────────────────
@pytest.mark.asyncio
async def test_client_raises_on_466(monkeypatch):
    from app.services.green_api import GreenAPIClient
    client = GreenAPIClient("770022680000", "token")

    async def _fake_call():
        req = httpx.Request("POST", "https://api.green-api.com/x")
        return httpx.Response(QUOTA_STATUS_CODE, request=req, json={})
    with pytest.raises(GreenQuotaExceeded):
        await client._guarded(_fake_call)
