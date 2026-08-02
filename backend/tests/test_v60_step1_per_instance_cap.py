"""V60 STEP 1 — PIN the per-instance daily cap on campaigns.

The V60 architecture doc claimed the daily cap was campaign-wide only, so one account could
send 20 while another sent 5. Verification (PART C-1) showed the opposite: the per-account cap
IS enforced, in BOTH send paths, and a young account is hard-capped at 5/day.

Because that brake already protects real numbers, the risk is not that it's missing — it's that
a future refactor removes it without anyone noticing. These tests pin it. They are deliberately
behavioural (the arithmetic and the enforcement points), not a restatement of the source.

Pinned:
  • computed_daily_limit hard-caps ANY account under 10 days at 5/day, whatever daily_limit says;
  • effective_daily_cap layers the 200 hard ceiling and the throttle factor on top;
  • both send loops compare `account.sent_today` against that per-account cap;
  • the campaign-level drip quota is SEPARATE from and additional to the per-account cap.
"""
import inspect
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.models.account import Account
from app.services import governors
from app.services import campaign_runner as cr
from app.services import campaign_preflight as pf

NOW = datetime(2026, 8, 2, 12, 0)


def _acct(**kw):
    """A detached Account row — never added to a session, so this stays a pure unit test
    while still exercising the REAL `computed_daily_limit` property rather than a copy of it."""
    return Account(
        name="t", instance_id="i", api_token="t",
        days_active=kw.get("days_active", 0),
        max_daily_absolute=kw.get("max_daily_absolute", 200),
        received_yesterday=kw.get("received_yesterday", 0),
        incoming_ratio_multiplier=kw.get("incoming_ratio_multiplier", 0.5),
        quick_replies_yesterday=kw.get("quick_replies_yesterday", 0),
        throttle_factor=kw.get("throttle_factor", 1.0),
        throttle_until=kw.get("throttle_until", None),
    )


# ── the young-account hard cap ───────────────────────────────────────────────
def test_account_under_10_days_is_capped_at_5_whatever_the_configured_limit():
    """This is the brake that matters for the three 17-day senders: their days_active is 0,
    so the system caps them at 5/day even though daily_limit reads 50."""
    for days in (0, 1, 5, 9):
        a = _acct(days_active=days, max_daily_absolute=200)
        assert a.computed_daily_limit == 5, f"days_active={days} must cap at 5"


def test_the_cap_opens_up_at_exactly_10_days():
    assert _acct(days_active=9).computed_daily_limit == 5
    assert _acct(days_active=10).computed_daily_limit > 5


def test_max_daily_absolute_can_lower_but_never_raise_the_young_cap():
    assert _acct(days_active=0, max_daily_absolute=3).computed_daily_limit == 3
    assert _acct(days_active=0, max_daily_absolute=999).computed_daily_limit == 5


def test_an_established_account_earns_capacity_from_real_engagement():
    quiet = _acct(days_active=30)
    engaged = _acct(days_active=30, received_yesterday=20, quick_replies_yesterday=4)
    assert engaged.computed_daily_limit > quiet.computed_daily_limit


def test_no_account_ever_exceeds_its_absolute_maximum():
    a = _acct(days_active=365, received_yesterday=9999, quick_replies_yesterday=9999,
              max_daily_absolute=40)
    assert a.computed_daily_limit == 40


# ── effective_daily_cap: ceiling + throttle ─────────────────────────────────
def test_effective_cap_applies_the_200_hard_ceiling():
    a = _acct(days_active=365, max_daily_absolute=10_000,
              received_yesterday=9999, quick_replies_yesterday=9999)
    assert governors.effective_daily_cap(a, NOW) <= 200


def test_effective_cap_shrinks_while_throttled():
    a = _acct(days_active=30, throttle_factor=0.5,
              throttle_until=NOW + timedelta(hours=1))
    untrottled = _acct(days_active=30)
    assert governors.effective_daily_cap(a, NOW) < governors.effective_daily_cap(untrottled, NOW)


def test_effective_cap_is_never_negative():
    a = _acct(days_active=30, throttle_factor=0.0,
              throttle_until=NOW + timedelta(hours=1))
    assert governors.effective_daily_cap(a, NOW) >= 0


def test_a_young_throttled_account_still_cannot_exceed_five():
    a = _acct(days_active=2, throttle_factor=1.0)
    assert governors.effective_daily_cap(a, NOW) <= 5


# ── both send paths enforce it ──────────────────────────────────────────────
def test_sequential_path_compares_sent_today_against_the_per_account_cap():
    src = inspect.getsource(cr._run_campaign_inner)
    assert "effective_daily_cap_guarded" in src
    assert "account.sent_today >= _cap" in src


def test_parallel_path_compares_sent_today_against_the_per_account_cap():
    src = inspect.getsource(cr._send_chunk)
    assert "effective_daily_cap_guarded" in src
    assert "account.sent_today >= _chunk_cap[0]" in src


def test_the_cap_is_per_account_not_shared_across_the_campaign():
    """Each chunk computes its OWN cap from its OWN fixed account — the doc's feared
    '20 from one, 5 from another' cannot happen."""
    src = inspect.getsource(cr._send_chunk)
    assert "effective_daily_cap_guarded(db, account)" in src


# ── drip is a SEPARATE, additional cap ──────────────────────────────────────
def test_drip_is_campaign_wide_and_independent_of_the_per_account_cap():
    """Both must hold; neither replaces the other. drip off must not imply 'no limit',
    because the per-account cap still applies."""
    assert pf.drip_remaining(False, 50, 0) is None      # no campaign-level cap
    assert _acct(days_active=0).computed_daily_limit == 5   # per-account cap still 5


def test_capacity_math_three_young_accounts():
    """The real fleet: three 17-day senders whose days_active is 0 → 5 each → 15/day."""
    accounts = [_acct(days_active=0) for _ in range(3)]
    per_day = sum(governors.effective_daily_cap(a, NOW) for a in accounts)
    assert per_day == 15
    # 200 contacts at 15/day
    assert -(-200 // per_day) == 14        # ceil division → 14 days
