"""V13.4 — opt-out keyword detection (configurable, digit-normalized)."""

# Default opt-out keywords (a message equal to one of these = opt-out).
OPT_OUT_KEYWORDS = {"۱۱", "11", "لغو", "لغو۱۱", "لغو ۱۱", "stop", "unsubscribe", "لغو عضویت"}

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _norm(text: str) -> str:
    return (text or "").translate(_PERSIAN_DIGITS).translate(_ARABIC_DIGITS).strip().lower()


_NORMALIZED_KEYWORDS = {_norm(k) for k in OPT_OUT_KEYWORDS}


def is_opt_out(text: str) -> bool:
    """True if the whole (trimmed, digit-normalized) message is an opt-out keyword.
    Exact match avoids false positives like 'لغو نکن' (don't cancel)."""
    if not text:
        return False
    return _norm(text) in _NORMALIZED_KEYWORDS
