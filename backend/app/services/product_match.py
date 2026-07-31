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

_CATEGORY_ALIASES = {
    "dishwasher": {"ظرفشویی", "ماشین ظرفشویی"},
    "washing_machine": {"لباسشویی", "ماشین لباسشویی"},
    "vacuum": {"جاروبرقی"},
    "fridge": {"یخچال", "فریزر", "ساید"},
    "tv": {"تلویزیون"},
    "air_conditioner": {"کولر", "کولرگازی", "گازی", "اسپلیت", "پنل"},
    "microwave": {"مایکروفر", "مایکروویو"},
}
_CATEGORY_WORD_TO_KEY = {
    word: key for key, words in _CATEGORY_ALIASES.items() for word in words
}

_AD_WORDS = {
    "تومان", "ریال", "قیمت", "فروش", "موجود", "موجودی", "ارسال", "گارانتی",
    "ضمانت", "تحویل", "نقد", "اقساط", "خرید", "پیشنهاد", "تخفیف", "همکار",
}
_MONEY_WORDS = {"تومان", "تومن", "ریال", "میلیون"}
_FINANCE_ONLY_WORDS = {
    "واریز", "واریزی", "مبلغ", "فیش", "حساب", "حسابداری", "پذیرفته", "پرداخت",
    "کارت", "رسید", "بانک", "شبا", "تسویه", "مانده", "بدهی", "طلب",
}
_MERGE_STOPWORDS = _STOPWORDS | _PRODUCT_WORDS | _AD_WORDS | _MONEY_WORDS | _FINANCE_ONLY_WORDS | {
    "ماشین", "اصل", "ترکیه", "ترک", "آلمان", "آلمانی", "چین", "چینی", "سری",
    "مدل", "نفره", "قیمت", "موجود", "موجودی", "سفید", "مشکی", "استیل", "سیلور",
    "نقره", "طلایی", "دودی", "زولیت", "zeolith", "عدد", "دستگاه",
}
_NOISE_WORDS = {
    "سلام", "درود", "وقت", "بخیر", "ممنون", "لطفا", "لطفاً", "تماس", "واتساپ",
    "whatsapp", "wa", "http", "https", "لینک", "شماره", "آدرس",
}
# V49 PART 3 — Persian-script catalog tokens that are descriptors/colors/origins/series/sizes, NOT
# brands. Subtracted from the catalog-derived brand lexicon so a generic word can't act as a brand
# and let ordinary chat slip through the capacity+brand branch. «سام» (3 letters, also the given name
# "Sam") is excluded as too ambiguous; distinctive short brands like «گلد»/«بوش»/«بکو» are kept.
_NON_BRAND_TOKENS = {
    "ماشین", "کیلویی", "سیلور", "ساید", "دودی", "هزار", "اسپرسوساز", "چین", "کره",
    "مات", "دوقلو", "شکار", "مکس", "گرند", "پلاتینیوم", "استیل", "دیجیتال", "میلان",
    "ساز", "چایساز", "آبمیوه", "سام", "نقره", "طوسی", "دلستر",
    # generic verbs/adjectives and mis-merged compound tokens seen in catalog names — not brands
    "ساخت", "سرخ", "پلاس", "بای", "کوخ", "ویامی", "اتوبخارگر", "میرجنرال", "چایسازجنرال",
}


def _looks_persian(token: str) -> bool:
    return any("؀" <= ch <= "ۿ" for ch in (token or ""))


def catalog_brand_tokens(products: list) -> set:
    """V49 PART 3 — derive a brand lexicon from the EXISTING catalog product names (no hand-authored
    brand list). Keeps distinctive Persian-script brand words (یونیوا/جنرال/گلد/بوش/سامسونگ/هایسنس/
    ایوولی/بکو/الجی/دلونگی/فیلیپس/برلین…) and drops generic descriptors, latin model/series codes
    (handled by the model-code path), digits, and the project's existing stop/product/ad word-sets.
    So detection only learns brands the business actually deals in — nothing hardcoded from scratch."""
    brands: set[str] = set()
    for p in products or []:
        for w in _TOKEN_RE.findall((p.get("name") or "").translate(_DIGIT_TRANS).lower()):
            if len(w) < 3 or not _looks_persian(w):
                continue                                   # latin tokens are model/series codes
            if any(ch.isdigit() for ch in w):
                continue
            if (w in _STOPWORDS or w in _PRODUCT_WORDS or w in _AD_WORDS or w in _MONEY_WORDS
                    or w in _FINANCE_ONLY_WORDS or w in _NOISE_WORDS or w in _NON_BRAND_TOKENS):
                continue
            brands.add(w)
    return brands


_BULLET_PREFIX_RE = re.compile(r"^[\s\-–—•▪▫*✅🔥⭐️🌟📌🔸🔹:؛،,.]+")
_PHONE_RE = re.compile(r"(?:\+?98|0)?9\d{9}")
_PRICE_TAIL_RE = re.compile(
    r"(?:(?:قیمت|فروش|نقد|همکار)\s*[:：]?\s*)?"
    r"[\d,./\s]{4,}\s*(?:تومان|ریال|تومن|میلیون).*",
    re.IGNORECASE,
)


def _tokenize(text: str) -> set:
    return set(_TOKEN_RE.findall((text or "").translate(_DIGIT_TRANS).lower()))


def product_group_key(name: str) -> str:
    """V44 — canonical key for grouping near-identical product NAMES into one report row.

    Composes the project's EXISTING normalizers, so no new/divergent normalization is introduced:
      1. group_detection.normalize_fa — unifies Arabic→Persian letters (ي/ی, ك/ک, ى/ی…), maps
         Persian/Arabic digits to ASCII, strips diacritics/tatweel, case-folds, collapses whitespace.
      2. the same _TOKEN_RE used for catalog matching — keeps only word tokens (ordered), so spacing,
         punctuation, and ZWNJ differences collapse too.
    So «ال‌جی»/«ال جی», «سری 8»/«سری ۸», «NC701»/«Nc701», «پارتى»/«پارتی» share one key, while
    genuinely different products do not. Returns "" for an empty/None name."""
    from app.services.group_detection import normalize_fa
    return " ".join(_TOKEN_RE.findall(normalize_fa(name)))


def _ordered_tokens(name: str) -> list[str]:
    from app.services.group_detection import normalize_fa
    return _TOKEN_RE.findall(normalize_fa(name))


def _category_for_tokens(tokens: list[str]) -> str | None:
    token_set = set(tokens)
    compact = "".join(tokens)
    for word, key in _CATEGORY_WORD_TO_KEY.items():
        if word in token_set or word.replace(" ", "") in compact:
            return key
    return None


def _normalize_model_code(token: str) -> str | None:
    """Return a merge-safe model core.

    Keeps genuinely different model families separate, while collapsing common ad/catalog
    shorthand such as SMS46NW01 ↔ 46NW01B. The dropped SMS prefix is an appliance-series prefix
    in local Bosch dishwasher listings; a trailing single letter is commonly a color/market suffix.
    """
    t = (token or "").translate(_DIGIT_TRANS).upper()
    t = re.sub(r"[^0-9A-Z]", "", t)
    if not (len(t) >= 4 and any(c.isalpha() for c in t) and any(c.isdigit() for c in t)):
        return None
    for prefix in ("SMS", "WAT", "ASW"):
        if t.startswith(prefix) and len(t) > len(prefix) + 3:
            t = t[len(prefix):]
            break
    if len(t) >= 6 and t[-1].isalpha() and any(c.isdigit() for c in t[:-1]):
        # Color/market suffix: 46NW01B -> 46NW01. Does not alter SMS88TI46M because
        # after removing no prefix its core does not end in a digit-bearing base model of this shape.
        if re.match(r"^\d{2}[A-Z]{2}\d{2}[A-Z]$", t):
            t = t[:-1]
    return t


def _model_codes(tokens: list[str]) -> list[str]:
    seen, out = set(), []
    for tok in tokens:
        m = _normalize_model_code(tok)
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


def product_canonical_key(name: str) -> str:
    """A stronger product-identity key for report merging.

    `product_group_key` intentionally only merges spelling variants. This key extracts product
    identity: category + brand-like tokens + normalized model core when present. It is still
    conservative: different capacities/model cores remain separate, but noisy ad wording and
    shorthand model spellings collapse into one report row.
    """
    tokens = _ordered_tokens(name)
    if not tokens:
        return ""
    category = _category_for_tokens(tokens)
    models = _model_codes(tokens)
    brandish = []
    for t in tokens:
        if t in _MERGE_STOPWORDS:
            continue
        if _normalize_model_code(t):
            continue
        if t.isdigit():
            # Capacities are identity when no model exists; with a model they are usually noise.
            if not models and len(t) >= 4:
                brandish.append(t)
            continue
        if len(t) >= 3:
            brandish.append(t)
    # Preserve order but dedupe.
    dedup_brandish = list(dict.fromkeys(brandish))
    if models:
        parts = [category or "product"] + dedup_brandish[:2] + models[:2]
        return "|".join(parts)
    if category:
        parts = [category] + dedup_brandish[:4]
        return "|".join(parts)
    return product_group_key(name)


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
    t = (token or "").translate(_DIGIT_TRANS).lower()
    if any(w in t for w in _MONEY_WORDS):
        return False
    return len(t) >= 5 and any(c.isalpha() for c in t) and any(c.isdigit() for c in t)


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


def _looks_like_unknown_product_line(line: str, *, brands: set | None = None) -> bool:
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
    has_finance_only_word = bool(toks & _FINANCE_ONLY_WORDS)
    # V49 PART 3 — a known catalog brand (جنرال/گلد/یونیوا/هایسنس…) present in the line. Lets us catch
    # the very common "<capacity> <brand> ... موجود/قیمت" listing that carries NO generic appliance
    # noun (کولر/پنل/اسپلیت) and NO ≥5-char model code, e.g. «۲۴ هزار جنرال گلد اکو موجود✅».
    has_brand = bool(toks & (brands or set()))
    if has_finance_only_word and not (has_product_word or has_capacity or has_model):
        return False
    return (
        (has_product_word and (has_capacity or has_model or has_price or has_ad_word))
        or (has_model and (has_price or has_ad_word))
        # Brand branch is deliberately narrow: a real BTU/capacity token AND a commerce signal
        # (ad word or an explicit price) must accompany the brand, so money/finance chatter — which
        # never carries these brand tokens — cannot slip through.
        or (has_brand and has_capacity and (has_ad_word or has_price))
    )


def is_reportable_product_name(name: str) -> bool:
    """Defense-in-depth for legacy report rows.

    New detections are filtered by _looks_like_unknown_product_line(), but old rows may already have
    stored finance/accounting text as a product name. Keep genuine product terms/model codes while
    hiding money-only or one-word generic fragments from the top-products report.
    """
    raw = (name or "").strip()
    if len(raw) < 4:
        return False
    low = raw.translate(_DIGIT_TRANS).lower()
    toks = _tokenize(raw)
    if not toks:
        return False
    has_product_word = bool(toks & _PRODUCT_WORDS)
    has_capacity = bool(re.search(r"\b(?:[1-9]\d{3,4}|[1-9]\d\s*هزار)\b", low))
    has_model = any(_is_strong(t) for t in toks)
    has_finance_only_word = bool(toks & _FINANCE_ONLY_WORDS)
    if has_finance_only_word and not (has_product_word or has_capacity or has_model):
        return False
    if len(toks) == 1 and not (has_product_word or has_capacity or has_model):
        return False
    return True


def extract_unknown_products(text: str, *, known_names: set[str] | None = None,
                             limit: int = 5, brands: set | None = None) -> list[dict]:
    """Extract advertised product titles that were not matched to the assistant catalog.

    This is intentionally conservative: it only accepts lines that look like commerce/product
    listings (model/capacity/price/product terms), so ordinary chat does not flood reports.
    `brands` (V49 PART 3) is the catalog-derived brand lexicon that additionally catches
    "<capacity> <brand> … موجود/قیمت" listings with no generic appliance noun or model code.
    """
    known_names = known_names or set()
    seen, out = set(), []
    for raw in re.split(r"[\n\r]+", text or ""):
        if not _looks_like_unknown_product_line(raw, brands=brands):
            continue
        name = _clean_unknown_candidate(raw)
        if len(name) < 4 or name in known_names:
            continue
        if not is_reportable_product_name(name):
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
    # V49 PART 3 — learn the brand vocabulary from the same catalog already passed in, so the unknown
    # extractor can recognise brand+capacity listings without any separate/hardcoded brand list.
    brands = catalog_brand_tokens(products)
    unknown = extract_unknown_products(text, known_names=known_names, limit=unknown_limit,
                                       brands=brands)
    return known + unknown
