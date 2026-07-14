"""V14 PART B — interactive-button helpers (validation, plain-text mirror, and
defensive webhook parsers). Pure functions so they are unit-testable and reused by
the campaign runner, the send endpoints, and the webhook handler.
"""
from typing import Optional

MAX_BUTTONS = 3
MAX_BUTTON_TEXT = 25
VALID_TYPES = {"reply", "copy", "call", "url"}
# per-type required extra field
_REQUIRED_FIELD = {"copy": "copyCode", "call": "phoneNumber", "url": "url"}

# Persian digits for the plain-text mirror
_FA = "۰۱۲۳۴۵۶۷۸۹"


def _fa_num(n: int) -> str:
    return str(n).translate(str.maketrans("0123456789", _FA))


def validate_buttons(buttons: list[dict]) -> None:
    """Raise ValueError (Persian) if the button config violates a hard constraint.
    - MAX 3 buttons
    - button text ≤ 25 chars
    - copy→copyCode, call→phoneNumber, url→url required
    """
    if not isinstance(buttons, list) or not buttons:
        raise ValueError("حداقل یک دکمه لازم است")
    if len(buttons) > MAX_BUTTONS:
        raise ValueError(f"حداکثر {MAX_BUTTONS} دکمه مجاز است")
    for i, b in enumerate(buttons, 1):
        if not isinstance(b, dict):
            raise ValueError(f"دکمه {i} نامعتبر است")
        btype = b.get("type", "reply")
        if btype not in VALID_TYPES:
            raise ValueError(f"نوع دکمه {i} نامعتبر است: {btype}")
        text = (b.get("buttonText") or "").strip()
        if not text:
            raise ValueError(f"متن دکمه {i} لازم است")
        if len(text) > MAX_BUTTON_TEXT:
            raise ValueError(f"متن دکمه {i} نباید بیش از {MAX_BUTTON_TEXT} کاراکتر باشد")
        req = _REQUIRED_FIELD.get(btype)
        if req and not b.get(req):
            raise ValueError(f"دکمه {i} ({btype}) نیازمند فیلد {req} است")


def normalize_buttons(buttons: list[dict]) -> list[dict]:
    """Ensure each button has a buttonId (fill sequential ids if missing) and only
    the fields Green API expects for its type."""
    out = []
    for i, b in enumerate(buttons, 1):
        btype = b.get("type", "reply")
        item = {
            "type": btype,
            "buttonId": str(b.get("buttonId") or i),
            "buttonText": (b.get("buttonText") or "").strip(),
        }
        req = _REQUIRED_FIELD.get(btype)
        if req:
            item[req] = b.get(req)
        out.append(item)
    return out


def build_button_mirror(buttons: list[dict]) -> str:
    """Plain-text mirror appended to the body so the message still works if the
    interactive buttons don't render (e.g. «\n\n۱) قیمت  ۲) موجودی»). Only
    reply-type choices are mirrored (copy/call/url are self-describing links)."""
    labels = [b.get("buttonText", "").strip() for b in buttons
              if b.get("type", "reply") == "reply" and b.get("buttonText")]
    if not labels:
        return ""
    parts = [f"{_fa_num(i)}) {t}" for i, t in enumerate(labels, 1)]
    return "\n\n" + "  ".join(parts)


def parse_button_reply(payload: dict) -> Optional[dict]:
    """Extract a pressed-button reply from an incoming webhook, tolerant of all
    shapes: the new interactiveButtons / interactiveButtonsReply typeMessage and the
    legacy buttonsResponseMessage. Returns {button_id, button_text, message_id} or None.
    Never raises on missing keys."""
    data = payload.get("messageData", {}) or {}
    tm = data.get("typeMessage", "")

    # legacy shape
    if tm == "buttonsResponseMessage" or data.get("buttonsResponseMessage"):
        b = data.get("buttonsResponseMessage", {}) or {}
        bid = b.get("selectedButtonId")
        btext = b.get("selectedDisplayText")
        if bid or btext:
            return {"button_id": bid or "", "button_text": btext or "",
                    "message_id": payload.get("idMessage", "")}

    # new interactive shapes — the pressed button is the first (only) in `buttons`
    for key in ("interactiveButtonsReply", "interactiveButtons"):
        block = data.get(key)
        if isinstance(block, dict):
            btns = block.get("buttons") or []
            if btns and isinstance(btns[0], dict):
                first = btns[0]
                return {
                    "button_id": str(first.get("buttonId") or ""),
                    "button_text": first.get("buttonText") or block.get("contentText") or "",
                    "message_id": payload.get("idMessage", ""),
                }
            # some payloads carry the chosen id directly on the block
            if block.get("buttonId") or block.get("selectedButtonId"):
                return {
                    "button_id": str(block.get("buttonId") or block.get("selectedButtonId") or ""),
                    "button_text": block.get("buttonText") or block.get("contentText") or "",
                    "message_id": payload.get("idMessage", ""),
                }
    return None


def parse_reaction(payload: dict) -> Optional[dict]:
    """Extract an incoming reaction (typeMessage == 'reactionMessage'). Returns
    {emoji, reacted_message_id} or None. Never raises."""
    data = payload.get("messageData", {}) or {}
    if data.get("typeMessage") != "reactionMessage" and not data.get("reactionMessage"):
        return None
    block = data.get("reactionMessage", {}) or {}
    # Green API variants: emoji under 'text'/'emoji'; target under quotedMessage/stanzaId
    emoji = block.get("text") or block.get("emoji") or ""
    quoted = block.get("quotedMessage", {}) or {}
    reacted_id = (block.get("reactedMessageId") or block.get("stanzaId")
                  or quoted.get("stanzaId") or quoted.get("idMessage") or "")
    if not emoji and not reacted_id:
        return None
    return {"emoji": emoji, "reacted_message_id": reacted_id}
