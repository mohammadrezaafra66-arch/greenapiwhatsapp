"""Smoke tests for V4 Green API expansion."""
import inspect
from app.services.green_api import GreenAPIClient
from app.models.inbox import ChatJournal, UploadedFile


def test_v4_new_client_methods():
    methods = [
        "send_typing", "edit_message", "delete_message", "upload_file",
        "download_file", "get_webhooks_count", "clear_webhooks_queue",
        "get_message", "last_incoming_messages", "last_outgoing_messages",
        "get_chats", "set_disappearing_chat", "get_messages_count",
        "add_contact", "delete_contact", "update_group_name",
        "set_group_admin", "remove_group_admin", "leave_group",
        "set_group_picture", "send_voice_status", "delete_status",
        "get_incoming_statuses", "get_outgoing_statuses", "update_api_token",
    ]
    for m in methods:
        assert hasattr(GreenAPIClient, m), f"Missing: {m}"
        assert inspect.iscoroutinefunction(getattr(GreenAPIClient, m)), f"Not async: {m}"


def test_new_models_importable():
    assert ChatJournal.__tablename__ == "chat_journals"
    assert UploadedFile.__tablename__ == "uploaded_files"


def test_inbox_message_has_new_fields():
    from app.models.inbox import InboxMessage
    assert hasattr(InboxMessage, "call_status")
    assert hasattr(InboxMessage, "button_reply_id")
    assert hasattr(InboxMessage, "poll_votes")
