"""Product-mention matching for group messages.

The old logic required a message to contain a full product NAME (avg 41 chars)
as a substring — which never matched real chat. This instead builds per-product
"signature" tokens from the name and matches on:
  • a distinctive keyword (brand-ish word) AND a capacity/model token, or
  • a standalone strong model code (e.g. BE_6500EIG).
Matching is on whole tokens (word boundaries), not raw substrings, so "18000"
won't match inside "180000".
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

_TOKEN_RE = re.compile(r"[0-9a-z؀-ۿ]+(?:[-_][0-9a-z؀-ۿ]+)*")


def _tokenize(text: str) -> set:
    return set(_TOKEN_RE.findall((text or "").lower()))


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
            hits.append(name)
    return hits
