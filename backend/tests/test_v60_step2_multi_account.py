"""V60 PART A — send from exactly these accounts, and no others.

Before this the only expressible choices were ONE account (`selected_account_id`) or, with
`parallel_accounts=True`, EVERY active account. An operator who wanted three ended up blasting
from all of them — the opposite of what they asked for, and the pattern that concentrates
volume on whichever numbers happen to be healthiest that hour.

`selected_account_ids` (JSONB) is now the authority, honoured in EVERY mode. The invariant from
V18 PART 1 is unchanged and must stay unchanged: a selection can only ever NARROW the sending
set. These tests pin both the new capability and that old guarantee.
"""
import uuid
from types import SimpleNamespace

import pytest

from app.api.v1.campaigns import _clean_account_ids
from app.services.account_selection import (
    selected_account_ids, filter_to_selection, assert_sending_subset,
    resolve_sending_accounts, FanOutGuardError, SELECTED_ACCOUNT_UNAVAILABLE_REASON,
)


def _acc(**kw):
    return SimpleNamespace(id=kw.pop("id", uuid.uuid4()), instance_id=kw.pop("instance_id", "i"), **kw)


def _camp(parallel=False, selected=None, multi=None):
    return SimpleNamespace(parallel_accounts=parallel, selected_account_id=selected,
                           selected_account_ids=multi)


# ── the new capability ───────────────────────────────────────────────────────
def test_multi_selection_is_honoured():
    a, b, c = _acc(), _acc(), _acc()
    got = selected_account_ids(_camp(multi=[str(a.id), str(b.id)]))
    assert got == {str(a.id), str(b.id)}
    assert str(c.id) not in got


def test_multi_selection_wins_even_in_parallel_mode():
    """This is the whole point: "send concurrently from THESE three" was impossible before —
    parallel mode always meant every active account."""
    a, b = _acc(), _acc()
    got = selected_account_ids(_camp(parallel=True, multi=[str(a.id), str(b.id)]))
    assert got == {str(a.id), str(b.id)}


def test_multi_selection_overrides_a_stale_single_selection():
    a, b, old = _acc(), _acc(), _acc()
    got = selected_account_ids(_camp(selected=old.id, multi=[str(a.id), str(b.id)]))
    assert got == {str(a.id), str(b.id)}
    assert str(old.id) not in got


# ── legacy behaviour is untouched ───────────────────────────────────────────
def test_empty_multi_selection_falls_back_to_legacy():
    a = _acc()
    assert selected_account_ids(_camp(selected=a.id, multi=[])) == {a.id}
    assert selected_account_ids(_camp(selected=a.id, multi=None)) == {a.id}
    assert selected_account_ids(_camp(parallel=True, multi=[])) is None


def test_parallel_with_no_selection_still_means_all():
    assert selected_account_ids(_camp(parallel=True)) is None


# ── UUID objects and strings must be interchangeable ────────────────────────
def test_string_ids_match_uuid_account_rows():
    """The column is JSONB (strings); ORM rows carry UUID objects. Comparing them raw would
    match nothing and abort the campaign as "no eligible account"."""
    a, b = _acc(), _acc()
    kept = filter_to_selection([a, b], {str(a.id)})
    assert kept == [a]


def test_subset_guard_accepts_string_ids():
    a = _acc()
    assert assert_sending_subset([a], {str(a.id)}) == [a]


def test_subset_guard_still_catches_an_escape():
    a, intruder = _acc(), _acc()
    with pytest.raises(FanOutGuardError):
        assert_sending_subset([a, intruder], {str(a.id)})


# ── resolution: narrows, never widens ───────────────────────────────────────
def test_resolve_returns_only_the_chosen_healthy_accounts():
    a, b, c = _acc(), _acc(), _acc()
    accounts, abort = resolve_sending_accounts([a, b, c], _camp(multi=[str(a.id), str(c.id)]))
    assert abort is None
    assert {x.id for x in accounts} == {a.id, c.id}


def test_resolve_drops_a_chosen_account_that_is_not_eligible():
    """An account that went unhealthy is removed; the rest of the selection continues (A-3)."""
    a, b = _acc(), _acc()
    accounts, abort = resolve_sending_accounts([a], _camp(multi=[str(a.id), str(b.id)]))
    assert abort is None
    assert {x.id for x in accounts} == {a.id}


def test_resolve_aborts_when_every_chosen_account_is_unavailable():
    """Fail-closed: it must NEVER fall back to the accounts the user did not pick."""
    a, b, other = _acc(), _acc(), _acc()
    accounts, abort = resolve_sending_accounts([other], _camp(multi=[str(a.id), str(b.id)]))
    assert accounts == []
    assert abort == SELECTED_ACCOUNT_UNAVAILABLE_REASON


def test_a_selection_can_never_widen_the_sending_set():
    """Property: whatever is selected, the result is a subset of the eligible accounts AND of
    the selection itself."""
    accs = [_acc() for _ in range(5)]
    eligible = accs[:4]
    for size in range(1, 5):
        sel = [str(a.id) for a in accs[:size]]
        got, abort = resolve_sending_accounts(eligible, _camp(multi=sel))
        if abort:
            continue
        assert {x.id for x in got} <= {x.id for x in eligible}
        assert {str(x.id) for x in got} <= set(sel)


# ── input sanitising ────────────────────────────────────────────────────────
def test_clean_ids_normalises_and_dedupes():
    a = uuid.uuid4()
    assert _clean_account_ids([str(a), str(a).upper(), str(a)]) == [str(a)]


def test_clean_ids_drops_malformed_entries():
    a = uuid.uuid4()
    assert _clean_account_ids([str(a), "not-a-uuid", "", None]) == [str(a)]


def test_clean_ids_collapses_to_none_rather_than_an_empty_selection():
    """An empty list must mean "no restriction", not "match zero accounts" — otherwise a form
    that posts [] would silently stop the campaign from sending at all."""
    assert _clean_account_ids([]) is None
    assert _clean_account_ids(None) is None
    assert _clean_account_ids(["nonsense"]) is None


def test_clean_ids_preserves_order():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    assert _clean_account_ids([str(c), str(a), str(b)]) == [str(c), str(a), str(b)]
