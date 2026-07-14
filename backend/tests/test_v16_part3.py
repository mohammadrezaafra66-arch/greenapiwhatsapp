"""V16 PART 3 — advertising links: weighted selection, formatting, additive guarantee."""
import asyncio
import random
from types import SimpleNamespace
from app.services.adlinks import select_links, format_links_block, links_for_campaign


def _links():
    return [
        {"id": "a", "url": "https://t.me/afra", "title": "تلگرام", "weight": 8, "is_active": True},
        {"id": "b", "url": "https://instagram.com/afra", "title": "اینستاگرام", "weight": 2, "is_active": True},
        {"id": "c", "url": "https://x.com/afra", "title": "غیرفعال", "weight": 9, "is_active": False},
    ]


def test_ignores_inactive_and_caps_count():
    picked = select_links(_links(), count=5, mode="weighted")
    ids = {l["id"] for l in picked}
    assert "c" not in ids                 # inactive never chosen
    assert len(picked) == 2               # only 2 active → cap at 2


def test_no_duplicates_within_a_message():
    for _ in range(50):
        picked = select_links(_links(), count=2, mode="weighted")
        assert len({l["id"] for l in picked}) == len(picked)


def test_fixed_mode_is_top_weighted_deterministic():
    picked = select_links(_links(), count=1, mode="fixed")
    assert picked[0]["id"] == "a"         # weight 8 > 2 (c inactive)
    # deterministic across calls
    assert select_links(_links(), 1, "fixed")[0]["id"] == "a"


def test_weighted_distribution_tracks_weights():
    random.seed(1234)
    links = [
        {"id": "hi", "url": "u", "title": "t", "weight": 10, "is_active": True},
        {"id": "lo", "url": "u", "title": "t", "weight": 1, "is_active": True},
    ]
    counts = {"hi": 0, "lo": 0}
    for _ in range(2000):
        counts[select_links(links, 1, "weighted")[0]["id"]] += 1
    assert counts["hi"] > counts["lo"] * 3   # 10:1 weight → heavily favors "hi"


def test_format_block_shape():
    block = format_links_block([{"title": "تلگرام", "url": "https://t.me/afra"}])
    assert block.startswith("\n\n")
    assert "🔗 تلگرام: https://t.me/afra" in block
    assert format_links_block([]) == ""


def test_count_zero_or_empty_returns_nothing():
    assert select_links(_links(), 0, "weighted") == []
    assert select_links([], 3, "weighted") == []


# ── additive guarantee: toggle OFF → empty string appended ──────────────────
def test_links_for_campaign_off_is_empty():
    campaign = SimpleNamespace(append_links=False, links_count=3, links_mode="weighted")
    out = asyncio.run(links_for_campaign(campaign, db=None))   # db unused when off
    assert out == ""                       # byte-identical output guaranteed
