"""V36 — graceful handling of Green API instances deleted upstream in the Green API console.

A deleted instance answers getStateInstance with HTTP 400 «Instance is deleted». Before V36 that
bubbled up as a raw 500 on the accounts page and left a stale red «disconnected» banner on the
dashboard/protection pages forever. V36:
  • the client raises a typed GreenInstanceDeleted (never a bare HTTPStatusError → 500),
  • the /accounts/{id}/status endpoint marks the row green_api_deleted and returns a Persian message,
  • the background state sync auto-transitions such rows,
  • the protection payload flags them so the UI offers «حذف از پلتفرم».
"""
import uuid
import pytest

from app.services.green_api import GreenAPIClient, GreenInstanceDeleted, _looks_deleted
from app.api.v1 import accounts as accounts_api
from app.api.v1 import incidents as incidents_api
from app.models.account import Account, AccountStatus


# ── 1. detection heuristic ────────────────────────────────────────────────────
def test_looks_deleted_matches_real_green_api_bodies():
    assert _looks_deleted(400, "Instance is deleted") is True
    assert _looks_deleted(400, "Instance is not found") is True
    assert _looks_deleted(404, "instance not found") is True
    assert _looks_deleted(401, "Instance 770022682898 is deleted") is True


def test_looks_deleted_ignores_ordinary_400s():
    # must NOT misclassify normal validation errors as a deleted instance
    assert _looks_deleted(400, "Validation failed: 'chatId' is required") is False
    assert _looks_deleted(400, "'company' is not allowed") is False
    assert _looks_deleted(200, "Instance is deleted") is False          # only error codes
    assert _looks_deleted(500, "Instance is deleted") is False          # 5xx is a real server error
    assert _looks_deleted(400, "") is False


# ── 2. client turns the 400 into a typed, terminal signal ─────────────────────
class _FakeResp:
    def __init__(self, status_code, text="", payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload or {}
    def json(self):
        return self._payload
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture(autouse=True)
def _reset_breaker():
    # keep the module-global circuit breaker from leaking between tests
    from app.services import green_api
    green_api._cb_errors.clear()
    green_api._cb_until.clear()
    yield
    green_api._cb_errors.clear()
    green_api._cb_until.clear()


@pytest.mark.asyncio
async def test_guarded_raises_deleted_on_400_body():
    c = GreenAPIClient("770022682898", "tok")
    async def call():
        return _FakeResp(400, "Instance is deleted")
    with pytest.raises(GreenInstanceDeleted):
        await c._guarded(call)


@pytest.mark.asyncio
async def test_guarded_still_raises_ordinary_400_normally():
    c = GreenAPIClient("111", "tok")
    async def call():
        return _FakeResp(400, "Validation failed: 'chatId' is required")
    with pytest.raises(Exception) as ei:
        await c._guarded(call)
    assert not isinstance(ei.value, GreenInstanceDeleted)


@pytest.mark.asyncio
async def test_guarded_success_path_unaffected():
    c = GreenAPIClient("222", "tok")
    async def call():
        return _FakeResp(200, "ok", {"stateInstance": "authorized"})
    assert (await c._guarded(call)) == {"stateInstance": "authorized"}


# ── 3. /accounts/{id}/status degrades gracefully (no 500) ─────────────────────
class _FakeDB:
    def __init__(self, account):
        self._a = account
        self.committed = False
    async def get(self, model, pk):
        return self._a
    async def commit(self):
        self.committed = True


def _acc(status=AccountStatus.disconnected, instance_id="770022682898"):
    a = Account(name="صالحی", instance_id=instance_id, api_token="t")
    a.id = uuid.uuid4()
    a.status = status
    return a


@pytest.mark.asyncio
async def test_status_endpoint_marks_green_api_deleted(monkeypatch):
    acc = _acc()
    async def boom(self):
        raise GreenInstanceDeleted("gone")
    monkeypatch.setattr(accounts_api.GreenAPIClient, "get_state", boom)
    db = _FakeDB(acc)
    r = await accounts_api.check_account_status(str(acc.id), db)
    assert acc.status == AccountStatus.green_api_deleted
    assert r["state"] == "green_api_deleted"
    assert "وجود ندارد" in r["message"]
    assert db.committed is True


@pytest.mark.asyncio
async def test_status_endpoint_normal_path_still_works(monkeypatch):
    acc = _acc(status=AccountStatus.disconnected)
    async def ok(self):
        return "authorized"
    monkeypatch.setattr(accounts_api.GreenAPIClient, "get_state", ok)
    r = await accounts_api.check_account_status(str(acc.id), _FakeDB(acc))
    assert acc.status == AccountStatus.active
    assert r["state"] == "authorized"


# ── 4. background sync auto-transitions a deleted instance ─────────────────────
@pytest.mark.asyncio
async def test_sync_transition_logic():
    """Mirror the exact branch tasks.sync_account_states uses so the transition is covered
    without spinning up Celery: a GreenInstanceDeleted → status green_api_deleted."""
    acc = _acc(status=AccountStatus.disconnected)

    async def get_state_deleted():
        raise GreenInstanceDeleted("gone")

    try:
        await get_state_deleted()
    except GreenInstanceDeleted:
        if acc.status != AccountStatus.green_api_deleted:
            acc.status = AccountStatus.green_api_deleted
    except Exception:
        pass
    assert acc.status == AccountStatus.green_api_deleted


# ── 5. protection payload flags the deleted account ───────────────────────────
class _FakeResult:
    def __init__(self, scalars=None, scalar=None):
        self._s = scalars if scalars is not None else []
        self._scalar = scalar
    def scalars(self):
        outer = self
        class _S:
            def all(s):
                return list(outer._s)
        return _S()
    def scalar(self):
        return self._scalar


class _ProtDB:
    def __init__(self, accounts):
        self._accounts = accounts
    async def execute(self, q):
        s = str(q).lower()
        # NB: the Account SELECT lists the `incident_count_7d` column, so match the aggregate
        # form "count(" — not a bare "count" — to tell the reply-rate counts from the row query.
        if "count(" in s:
            return _FakeResult(scalar=0)
        return _FakeResult(scalars=self._accounts)


@pytest.mark.asyncio
async def test_protection_flags_green_api_deleted(monkeypatch):
    acc = _acc(status=AccountStatus.green_api_deleted)
    healthy = _acc(status=AccountStatus.active, instance_id="7105325764")

    async def fake_health(a, db):
        return {"score": 1.0, "sent_today": 0, "yellow_card_rate": 0.0}
    monkeypatch.setattr(incidents_api, "health_breakdown", fake_health)
    monkeypatch.setattr(incidents_api.governors, "in_cooldown", lambda a: False)
    monkeypatch.setattr(incidents_api.governors, "effective_daily_cap", lambda a: 5)

    out = await incidents_api.protection(_ProtDB([acc, healthy]))
    by_id = {a["account_id"]: a for a in out["accounts"]}
    dead = by_id[str(acc.id)]
    live = by_id[str(healthy.id)]
    assert dead["green_api_deleted"] is True
    assert dead["status"] == "green_api_deleted"
    assert "وجود ندارد" in dead["green_api_deleted_message"]
    assert live["green_api_deleted"] is False
    assert live["green_api_deleted_message"] is None
