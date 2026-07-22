"""Product-mention matching for WhatsApp messages.

The old logic required a message to contain a full product NAME (avg 41 chars)
as a substring — which never matched real chat. This instead builds per-product
"signature" tokens from the name and matches on:
  • a distinctive keyword (brand-ish word) AND a capacity/model token, or
  • a standalone strong model code (e.g. BE_6500EIG).
Matching is on whole tokens (word boundaries), not raw substrings, so "18000"
won't match inside "180000".

V40: when a message advertises a product that is NOT in the Afrakala assistant/catalog,
extract a clean product-like title from the message and mark it as outside the assistant.
"""
import re

# Generic appliance/HVAC words that are NOT distinctive brand keywords.
_STOPWORDS = {
    "مدل", "سرد", "وگرم", "گرم", "معمولی", "اینورتر", "کولر", "گازی", "موتور",
    "برق", "اسب", "بخار", "لوکس", "دیجیتال", "اسپلیت", "ایستاده", "پرتابل",
    "اکونومی", "اینچ", "لیتر", "کیلو", "وات", "ولت", "سری", "نوع", "رنگ",
    "سفید", "مشکی", "نقره", "طلایی", "دست", "دوم", "نو",
    "and", "the", "amp", "inverter", "titanium", "ultra", "utra", "cool", "hot",
}

_TOKEN_RE = re.compile(r"[0-9a-z\u0600-\u06FF]+(?:[-_][0-9a-z\u0600-\u06FF]+)*")
_DIGIT_TRANS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_PRODUCT_WORDS = {
    "کولر", "گازی", "اسپلیت", "اینورتر", "پنل", "موتور", "کمپرسور", "یخچال",
    "فریزر", "لباسشویی", "ظرفشویی", "تلویزیون", "اجاق", "مایکروفر", "جاروبرقی",
    "پنکه", "بخاری", "آبگرمکن", "پکیج", "چیلر", "داکت", "داکت‌اسپلیت", "کاندیشنر",
    "کولرگازی", "air", "conditioner", "split", "inverter",
}
_AD_WORDS = {
    "تومان", "ریال", "قیمت", "فروش", "موجود", "موجودی", "ارسال", "گارانتی",
    "ضمانت", "تحویل", "نقد", "اقساط", "خرید", "پیشنهاد", "تخفیف", "همکار",
}
_NOISE_WORDS = {
    "سلام", "درود", "وقت", "بخیر", "ممنون", "لطفا", "لطفاً", "تماس", "واتساپ",
    "whatsapp", "wa", "http", "https", "لینک", "شماره", "آدرس",
}
_BULLET_PREFIX_RE = re.compile(r"^[\s\-–—•▪▫*✅🔥⭐️🌟📌🔸🔹:؛،,.]+")
_PHONE_RE = re.compile(r"(?:\+?98|0)?9\d{9}")
_PRICE_TAIL_RE = re.compile(
    r"(?:(?:قیمت|فروش|نقد|همکار)\s*[:：]?\s*)?"
    r"[\d,./\s]{4,}\s*(?:تومان|ریال|تومن|میلیون).*",
    re.IGNORECASE,
)


def _tokenize(text: str) -> set:
    return set(_TOKEN_RE.findall((text or "").translate(_DIGIT_TRANS).lower()))


def product_tokens(name: str):
    """Return (keywords, hard_tokens) for a product name.
    keywords   = distinctive brand/word tokens (non-stopword, len>=3).
    hard_tokens = capacity numbers (>=4 digits) + model codes (alphanumeric/hyphen)."""
    keywords, hard = set(), set()
    for w in _TOKEN_RE.findall((name or "").lower()):
        if len(w) < 3 or w in _STOPWORDS:
            continue
        has_alpha = any(c.isalpha() for c in w)
        has_digit = any(c.isdigit() for c in w)
        if w.isdigit():
            if len(w) >= 4:  # BTU capacity like 9000..30000
                hard.add(w)
        elif ("-" in w or "_" in w) or (has_alpha and has_digit):
            hard.add(w)       # model code
            keywords.add(w)
        else:
            keywords.add(w)   # plain brand/keyword word
    return keywords, hard


def _is_strong(token: str) -> bool:
    # A distinctive alphanumeric model code is enough on its own.
    return len(token) >= 5 and any(c.isalpha() for c in token) and any(c.isdigit() for c in token)


def match_products(text: str, products: list) -> list:
    """Return the list of product names `text` plausibly mentions."""
    return [m["product_name"] for m in match_known_products(text, products)]


def match_known_products(text: str, products: list) -> list[dict]:
    """Return catalog-backed product mentions with product_id when available."""
    msg = _tokenize(text)
    if not msg:
        return []
    hits = []
    for p in products:
        name = p.get("name") or ""
        kws, hard = product_tokens(name)
        if not hard:
            continue
        hard_hit = hard & msg
        if not hard_hit:
            continue
        if any(_is_strong(h) for h in hard_hit) or (kws & msg):
            hits.append({
                "product_name": name,
                "product_id": str(p.get("id") or "") or None,
                "in_assistant": True,
                "source": "assistant",
            })
    return hits


def _clean_unknown_candidate(line: str) -> str:
    s = _BULLET_PREFIX_RE.sub("", (line or "").strip())
    s = re.sub(r"https?://\S+", "", s, flags=re.IGNORECASE)
    s = _PHONE_RE.sub("", s.translate(_DIGIT_TRANS))
    s = _PRICE_TAIL_RE.sub("", s).strip(" -–—:؛،,.")
    # Keep the recognizable product title, not a whole sales paragraph.
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > 90:
        s = s[:90].rsplit(" ", 1)[0].strip()
    return s


def _looks_like_unknown_product_line(line: str) -> bool:
    raw = (line or "").strip()
    if not raw or len(raw) < 5 or len(raw) > 220:
        return False
    low = raw.translate(_DIGIT_TRANS).lower()
    toks = _tokenize(raw)
    if not toks or len(toks & _NOISE_WORDS) >= 2:
        return False
    has_product_word = bool(toks & _PRODUCT_WORDS)
    has_ad_word = bool(toks & _AD_WORDS)
    has_capacity = bool(re.search(r"\b(?:[1-9]\d{3,4}|[1-9]\d\s*هزار)\b", low))
    has_model = any(_is_strong(t) for t in toks)
    has_price = bool(re.search(r"\d[\d,\s.]{3,}\s*(?:تومان|ریال|تومن|میلیون)", low))
    return (has_product_word and (has_capacity or has_model or has_price or has_ad_word)) or (
        has_model and (has_price or has_ad_word)
    )


def extract_unknown_products(text: str, *, known_names: set[str] | None = None,
                             limit: int = 5) -> list[dict]:
    """Extract advertised product titles that were not matched to the assistant catalog.

    This is intentionally conservative: it only accepts lines that look like commerce/product
    listings (model/capacity/price/product terms), so ordinary chat does not flood reports.
    """
    known_names = known_names or set()
    seen, out = set(), []
    for raw in re.split(r"[\n\r]+", text or ""):
        if not _looks_like_unknown_product_line(raw):
            continue
        name = _clean_unknown_candidate(raw)
        if len(name) < 4 or name in known_names:
            continue
        if any(k and (k in name or name in k) for k in known_names):
            continue
        key = " ".join(_tokenize(name))
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({
            "product_name": name,
            "product_id": None,
            "in_assistant": False,
            "source": "detected",
        })
        if len(out) >= limit:
            break
    return out


def detect_product_mentions(text: str, products: list, *, unknown_limit: int = 5) -> list[dict]:
    """Known catalog matches + unknown advertised products from a WhatsApp message."""
    known = match_known_products(text, products)
    known_names = {m["product_name"] for m in known}
    unknown = extract_unknown_products(text, known_names=known_names, limit=unknown_limit)
    return known + unknown
