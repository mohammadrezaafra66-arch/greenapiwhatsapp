"""Tests for the polling service's notification-processing contract."""
import pytest
from unittest.mock import AsyncMock, patch
from app.services.polling_service import poll_account_once


class FakeAccount:
    instance_id = "1101234567"
    api_token = "fake-token"
    name = "Test Account"


@pytest.mark.asyncio
async def test_poll_account_once_empty_queue():
    with patch("app.services.polling_service.GreenAPIClient") as MockClient:
        instance = MockClient.return_value
        instance.receive_notification = AsyncMock(return_value=None)
        result = await poll_account_once(FakeAccount())
        assert result == 0


@pytest.mark.asyncio
async def test_poll_account_once_processes_and_deletes():
    fake_notif = {"receiptId": 42, "body": {"typeWebhook": "stateInstanceChanged", "stateInstance": "authorized"}}
    with patch("app.services.polling_service.GreenAPIClient") as MockClient, \
         patch("app.services.polling_service.process_webhook", new_callable=AsyncMock) as mock_process:
        instance = MockClient.return_value
        instance.receive_notification = AsyncMock(return_value=fake_notif)
        instance.delete_notification = AsyncMock(return_value=True)

        result = await poll_account_once(FakeAccount())

        assert result == 1
        mock_process.assert_awaited_once_with("1101234567", fake_notif["body"])
        instance.delete_notification.assert_awaited_once_with(42)
