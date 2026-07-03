"""Smoke tests for V6 features."""
import inspect
from app.services.green_api import GreenAPIClient
from app.models.wa_extras import DisappearingChatSetting, WaBlockedContact


def test_v6_client_methods():
    methods = [
        "set_disappearing_chat", "get_contacts_block",
        "add_contact", "edit_contact", "delete_contact",
        "set_proxy", "remove_proxy", "get_proxy"
    ]
    for m in methods:
        assert hasattr(GreenAPIClient, m), f"Missing: {m}"
        assert inspect.iscoroutinefunction(getattr(GreenAPIClient, m)), f"Not async: {m}"


def test_v6_models():
    assert DisappearingChatSetting.__tablename__ == "disappearing_chat_settings"
    assert WaBlockedContact.__tablename__ == "wa_blocked_contacts"


def test_ephemeral_values():
    """Confirm valid ephemeral values."""
    valid = {0, 86400, 604800, 7776000}
    assert 0 in valid  # off
    assert 86400 in valid  # 24h
    assert 604800 in valid  # 7d
    assert 7776000 in valid  # 90d
