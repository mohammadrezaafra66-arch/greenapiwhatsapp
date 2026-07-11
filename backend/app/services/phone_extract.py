"""Extract phone numbers from free text (Persian/Arabic/English digits)."""
import re

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize_digits(text: str) -> str:
    return text.translate(PERSIAN_DIGITS).translate(ARABIC_DIGITS)


def normalize_iranian_mobile(digits: str) -> str | None:
    """Normalize to 09xxxxxxxxx if it's a valid Iranian mobile, else None."""
    d = re.sub(r"\D", "", digits)
    if d.startswith("98"):
        d = "0" + d[2:]
    elif d.startswith("9") and len(d) == 10:
        d = "0" + d
    if len(d) == 11 and d.startswith("09"):
        return d
    return None


def extract_phones_from_text(text: str) -> list[str]:
    """Find phone-like sequences in message text. Returns deduped normalized list."""
    if not text:
        return []
    t = normalize_digits(text)
    found: list[str] = []
    seen: set[str] = set()

    # Iranian mobile
    for m in re.findall(r"(?:\+?98|0)?9\d{9}", t):
        norm = normalize_iranian_mobile(m)
        if norm and norm not in seen:
            seen.add(norm)
            found.append(norm)

    # Landlines: 0xx(x) + 7-8 digits, optional separators
    for m in re.findall(r"0\d{2,3}[-\s]?\d{7,8}", t):
        d = re.sub(r"\D", "", m)
        if 10 <= len(d) <= 11 and not d.startswith("09") and d not in seen:
            seen.add(d)
            found.append(d)

    return found


def normalize_sender_phone(raw: str) -> str:
    """Normalize a stored sender phone (98xxxxxxxxxx or with @c.us) to 09xxxxxxxxx display."""
    if not raw:
        return ""
    d = re.sub(r"\D", "", raw.split("@")[0])
    norm = normalize_iranian_mobile(d)
    return norm or d


def contacts_for(sender_phone: str, message_text: str) -> tuple[str, list[str], list[str]]:
    """Shared helper: returns (sender_display, phones_in_message, all_contacts) —
    sender phone first, then any phones found inside the message text, deduped."""
    sender_display = normalize_sender_phone(sender_phone or "")
    phones_in_msg = extract_phones_from_text(message_text or "")
    all_contacts: list[str] = []
    for p in [sender_display] + phones_in_msg:
        if p and p not in all_contacts:
            all_contacts.append(p)
    return sender_display, phones_in_msg, all_contacts
