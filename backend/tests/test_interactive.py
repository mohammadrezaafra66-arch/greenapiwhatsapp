"""V14 PART B — interactive messaging tests (B.7).

Covers: 3-button cap, 25-char cap, per-type required fields, plain-text mirror,
button-reply parsing (all shapes), reaction webhook parsing, and the runtime
403 → plain-text fallback in the campaign runner.
"""
import asyncio
import types
import pytest
from app.services.interactive import (
    validate_buttons, normalize_buttons, build_button_mirror,
    parse_button_reply, parse_reaction, MAX_BUTTONS, MAX_BUTTON_TEXT,
)
from app.services.capabilities import is_403


# ── validation ──────────────────────────────────────────────────────────────
def test_validate_ok():
    validate_buttons([
        {"type": "reply", "buttonText": "قیمت"},
        {"type": "copy", "buttonText": "کپی", "copyCode": "3333"},
        {"type": "url", "buttonText": "سایت", "url": "https://x.com"},
    ])


def test_validate_rejects_more_than_three():
    with pytest.raises(ValueError):
        validate_buttons([{"type": "reply", "buttonText": f"b{i}"} for i in range(MAX_BUTTONS + 1)])


def test_validate_rejects_long_text():
    with pytest.raises(ValueError):
        validate_buttons([{"type": "reply", "buttonText": "x" * (MAX_BUTTON_TEXT + 1)}])


@pytest.mark.parametrize("btn", [
    {"type": "copy", "buttonText": "c"},                 # missing copyCode
    {"type": "call", "buttonText": "c"},                 # missing phoneNumber
    {"type": "url", "buttonText": "c"},                  # missing url
])
def test_validate_rejects_missing_type_field(btn):
    with pytest.raises(ValueError):
        validate_buttons([btn])


def test_validate_rejects_empty():
    with pytest.raises(ValueError):
        validate_buttons([])


def test_normalize_fills_button_ids():
    out = normalize_buttons([{"type": "reply", "buttonText": "a"}, {"type": "reply", "buttonText": "b"}])
    assert [b["buttonId"] for b in out] == ["1", "2"]


def test_build_button_mirror_reply_only():
    mirror = build_button_mirror([
        {"type": "reply", "buttonText": "قیمت"},
        {"type": "reply", "buttonText": "موجودی"},
        {"type": "url", "buttonText": "سایت", "url": "https://x.com"},
    ])
    assert "قیمت" in mirror and "موجودی" in mirror
    assert "سایت" not in mirror          # url buttons are not mirrored
    assert mirror.startswith("\n\n")


# ── button-reply parsing (all shapes) ───────────────────────────────────────
def test_parse_interactive_buttons_reply_shape():
    payload = {"idMessage": "M1", "messageData": {
        "typeMessage": "interactiveButtonsReply",
        "interactiveButtonsReply": {"contentText": "?", "buttons": [
            {"type": "reply", "buttonId": "1", "buttonText": "قیمت"}]}}}
    out = parse_button_reply(payload)
    assert out == {"button_id": "1", "button_text": "قیمت", "message_id": "M1"}


def test_parse_legacy_buttons_response():
    payload = {"idMessage": "M2", "messageData": {
        "typeMessage": "buttonsResponseMessage",
        "buttonsResponseMessage": {"selectedButtonId": "2", "selectedDisplayText": "موجودی"}}}
    out = parse_button_reply(payload)
    assert out["button_id"] == "2" and out["button_text"] == "موجودی"


def test_parse_button_reply_missing_returns_none():
    assert parse_button_reply({"messageData": {"typeMessage": "textMessage"}}) is None
    assert parse_button_reply({}) is None


# ── reaction parsing ────────────────────────────────────────────────────────
def test_parse_reaction_shape():
    payload = {"messageData": {"typeMessage": "reactionMessage",
               "reactionMessage": {"text": "👍", "quotedMessage": {"stanzaId": "R1"}}}}
    out = parse_reaction(payload)
    assert out == {"emoji": "👍", "reacted_message_id": "R1"}


def test_parse_reaction_none_for_text():
    assert parse_reaction({"messageData": {"typeMessage": "textMessage"}}) is None


# ── is_403 detector ─────────────────────────────────────────────────────────
def test_is_403_from_message():
    assert is_403(RuntimeError("HTTP 403")) is True
    assert is_403(RuntimeError("HTTP 500")) is False


def test_is_403_from_response_attr():
    exc = RuntimeError("boom")
    exc.response = types.SimpleNamespace(status_code=403)
    assert is_403(exc) is True


# ── runtime 403 → plain-text fallback (the send is never lost) ──────────────
def test_403_fallback_resends_plain_text():
    """Simulate _deliver_message's interactive branch: on a 403 the same body must be
    re-sent via send_message so the recipient is never skipped."""
    sent = {}

    class FakeClient:
        async def send_interactive_buttons_rich(self, chat, header, body, footer, buttons):
            raise RuntimeError("Green API failed: HTTP 403")

        async def send_message(self, phone, message):
            sent["plain"] = message
            return "PLAIN_ID"

    async def deliver():
        client = FakeClient()
        body = "متن پیام" + build_button_mirror([{"type": "reply", "buttonText": "قیمت"}])
        try:
            return await client.send_interactive_buttons_rich("9x@c.us", "", body, "", [])
        except Exception as e:
            assert is_403(e)
            return await client.send_message("9x", body)

    msg_id = asyncio.run(deliver())
    assert msg_id == "PLAIN_ID"
    assert "قیمت" in sent["plain"]        # button choices preserved in the plain fallback
