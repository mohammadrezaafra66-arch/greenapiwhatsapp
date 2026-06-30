"""Tests for the Green API client helpers."""
import pytest
from app.services.green_api import GreenAPIClient


@pytest.mark.parametrize("raw,expected", [
    ("09123456789", "989123456789"),
    ("+989123456789", "989123456789"),
    ("9123456789", "989123456789"),
    ("0912 345 6789", "989123456789"),
    ("0912-345-6789", "989123456789"),
    ("989123456789", "989123456789"),
])
def test_normalize_phone(raw, expected):
    assert GreenAPIClient._normalize_phone(raw) == expected


def test_base_url_built_from_instance():
    client = GreenAPIClient("1101234567", "token-abc")
    assert client.base_url == "https://api.green-api.com/waInstance1101234567"
    assert client.instance_id == "1101234567"
    assert client.api_token == "token-abc"


def test_new_methods_exist():
    import inspect
    from app.services.green_api import GreenAPIClient
    assert inspect.iscoroutinefunction(GreenAPIClient.send_file_upload)
    assert inspect.iscoroutinefunction(GreenAPIClient.unarchive_chat)
