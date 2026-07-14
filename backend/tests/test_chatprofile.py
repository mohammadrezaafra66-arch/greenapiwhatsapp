"""V14 PART D — chat & profile tests (Features 15, 16, 17, 18)."""
import asyncio
import pytest
from app.services.msgcontrol import valid_disappearing, DISAPPEARING_VALUES
from app.services.green_api import GreenAPIClient


# ── FEATURE 16 — disappearing values whitelist ──────────────────────────────
@pytest.mark.parametrize("v", sorted(DISAPPEARING_VALUES))
def test_disappearing_allowed_values(v):
    assert valid_disappearing(v) is True


@pytest.mark.parametrize("v", [1, 100, 3600, 999999, -1, "x", None, 86401])
def test_disappearing_rejects_others(v):
    assert valid_disappearing(v) is False


def test_disappearing_exact_set():
    assert DISAPPEARING_VALUES == {0, 86400, 604800, 7776000}


# ── client payload shapes ───────────────────────────────────────────────────
def _capture(client):
    calls = {}

    async def fake_post(endpoint, data=None, timeout=30):
        calls["endpoint"] = endpoint
        calls["data"] = data
        return {}

    client._post = fake_post
    return calls


def test_archive_unarchive_endpoints():
    c = GreenAPIClient("111", "tok")
    calls = _capture(c)
    asyncio.run(c.archive_chat_raw("120363@g.us"))
    assert calls["endpoint"] == "archiveChat"
    assert calls["data"]["chatId"] == "120363@g.us"      # group chatId passthrough

    calls2 = _capture(c)
    asyncio.run(c.unarchive_chat_raw("09123456789"))
    assert calls2["endpoint"] == "unarchiveChat"
    assert calls2["data"]["chatId"].endswith("@c.us")    # bare phone normalized


def test_set_disappearing_uses_ephemeral_expiration_key():
    c = GreenAPIClient("111", "tok")
    calls = _capture(c)
    asyncio.run(c.set_disappearing_raw("9891@c.us", 604800))
    assert calls["endpoint"] == "setDisappearingChat"
    assert calls["data"]["ephemeralExpiration"] == 604800


def test_get_contact_info_raw_shape():
    c = GreenAPIClient("111", "tok")
    calls = _capture(c)
    asyncio.run(c.get_contact_info_raw("9891@c.us"))
    assert calls["endpoint"] == "getContactInfo"
    assert calls["data"]["chatId"] == "9891@c.us"


def test_profile_picture_upload_is_multipart(monkeypatch):
    """setProfilePicture must POST multipart (field `file`), not JSON."""
    import app.services.green_api as g
    seen = {}

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"setProfilePicture": True, "urlAvatar": "https://x/y.jpg"}

    class _Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, files=None, **kw):
            seen["files"] = files
            seen["url"] = url
            return _Resp()

    monkeypatch.setattr(g.httpx, "AsyncClient", _Client)
    c = GreenAPIClient("111", "tok")
    out = asyncio.run(c.set_profile_picture_upload(b"IMG", "a.jpg"))
    assert "file" in seen["files"]                       # multipart field name
    assert seen["files"]["file"][1] == b"IMG"
    assert "setProfilePicture/tok" in seen["url"]
    assert out["urlAvatar"].startswith("https://")
