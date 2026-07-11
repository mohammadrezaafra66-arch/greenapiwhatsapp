"""V13.7 — ROI funnel + reply-rate math (pure)."""


def _reply_rate(replied, sent):
    return round(100 * replied / sent, 1) if sent else 0.0


def _funnel(rows):
    """rows: list of dicts with status/delivery_status/replied/outcome — mirror the endpoint."""
    sent = sum(1 for r in rows if r["status"] == "sent")
    delivered = sum(1 for r in rows if r["delivery_status"] in ("delivered", "read"))
    read = sum(1 for r in rows if r["delivery_status"] == "read")
    replied = sum(1 for r in rows if r["replied"])
    purchased = sum(1 for r in rows if r["outcome"] == "purchased")
    interested = sum(1 for r in rows if r["outcome"] == "interested")
    return {
        "funnel": {"sent": sent, "delivered": delivered, "read": read, "replied": replied, "purchased": purchased},
        "interested": interested, "purchased": purchased, "reply_rate": _reply_rate(replied, sent),
    }


def _rows():
    return [
        {"status": "sent", "delivery_status": "read", "replied": True, "outcome": "purchased"},
        {"status": "sent", "delivery_status": "read", "replied": True, "outcome": "interested"},
        {"status": "sent", "delivery_status": "delivered", "replied": False, "outcome": None},
        {"status": "sent", "delivery_status": "sent", "replied": False, "outcome": None},
        {"status": "failed", "delivery_status": "failed", "replied": False, "outcome": None},
    ]


def test_reply_rate():
    assert _reply_rate(2, 4) == 50.0
    assert _reply_rate(0, 0) == 0.0


def test_funnel_counts():
    r = _funnel(_rows())
    f = r["funnel"]
    assert f["sent"] == 4          # 4 sent (1 failed excluded)
    assert f["delivered"] == 3     # 2 read + 1 delivered
    assert f["read"] == 2
    assert f["replied"] == 2
    assert f["purchased"] == 1
    assert r["interested"] == 1
    assert r["reply_rate"] == 50.0  # 2 replied / 4 sent


def test_read_is_subset_of_delivered():
    r = _funnel(_rows())["funnel"]
    assert r["read"] <= r["delivered"] <= r["sent"]
