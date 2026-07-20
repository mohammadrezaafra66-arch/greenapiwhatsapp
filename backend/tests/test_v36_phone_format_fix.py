"""V36 PART 3 fix — canonicalize phone formats so 09… contacts are matchable + backfill + retro.

PART 3's diagnosis: `handle_helper_incoming` compared the incoming WhatsApp chatId (always
international 98…) against a raw stored contact phone. Contacts saved local (09…) never matched, so
their completions were silently missed. This proves:
  • normalize_intl_phone canonicalizes 0…/9…/98… (+ Persian numerals, @c.us) to one intl form;
  • phone_match_forms yields every equivalent form so an incoming matches any stored format;
  • the backfill rewrites existing rows to intl without losing data;
  • end-to-end, a 09-stored contact now matches a 98-format incoming and its task goes `done`.
"""
import uuid
from datetime import datetime
from types import SimpleNamespace
import pytest

from app.services import warmup_helper_service as hs
from app.services import warmup_helper_engine as he
from app.models.warmup_helpers import WarmupHelper, WarmupHelperTask


# ── normalize_intl_phone ─────────────────────────────────────────────────────
def test_normalize_local_to_international():
    assert hs.normalize_intl_phone("09129484023") == "989129484023"   # local 0… → 98…
    assert hs.normalize_intl_phone("9129484023") == "989129484023"    # bare 9… (10) → 98…
    assert hs.normalize_intl_phone("989129484023") == "989129484023"  # already intl → unchanged


def test_normalize_strips_formatting_and_persian_digits():
    assert hs.normalize_intl_phone("+98 912 948 4023") == "989129484023"
    assert hs.normalize_intl_phone("989129484023@c.us") == "989129484023"
    assert hs.normalize_intl_phone("۰۹۱۲۹۴۸۴۰۲۳") == "989129484023"   # Persian numerals
    assert hs.normalize_intl_phone(None) == ""
    assert hs.normalize_intl_phone("") == ""


def test_normalize_is_idempotent():
    once = hs.normalize_intl_phone("09129484023")
    assert hs.normalize_intl_phone(once) == once


# ── phone_match_forms ────────────────────────────────────────────────────────
def test_match_forms_cover_all_equivalent_formats():
    forms = set(hs.phone_match_forms("989129484023"))   # incoming international
    assert "989129484023" in forms      # intl (backfilled rows)
    assert "09129484023" in forms       # legacy local rows
    assert "9129484023" in forms        # bare national rows
    # a contact stored in ANY of these formats is matched by an international incoming:
    for stored in ("989129484023", "09129484023", "9129484023"):
        assert stored in forms


def test_match_forms_from_local_incoming_also_matches_intl_stored():
    # symmetric: even if the incoming were local, the intl-stored contact still matches
    assert "989129484023" in set(hs.phone_match_forms("09129484023"))


def test_match_forms_empty_for_blank():
    assert hs.phone_match_forms(None) == []
    assert hs.phone_match_forms("") == []


# ── backfill ─────────────────────────────────────────────────────────────────
class _Res:
    def __init__(self, rows): self._rows = rows
    def scalars(self):
        outer = self
        class _S:
            def all(s): return list(outer._rows)
        return _S()


class _BackfillDB:
    def __init__(self, helpers): self._h = helpers; self.commits = 0
    async def execute(self, q): return _Res(self._h)
    async def commit(self): self.commits += 1


def _helper(name, phone, secondary=None):
    h = WarmupHelper(name=name, phone=phone, phone_secondary=secondary, is_active=True)
    h.id = uuid.uuid4()
    return h


@pytest.mark.asyncio
async def test_backfill_converts_local_rows_and_preserves_intl():
    h_local = _helper("پروین رضایی", "09129484023")
    h_intl = _helper("جبار افرا", "989121015426")
    h_sec = _helper("مینا معزز", "09101764710", secondary="09129373764")
    db = _BackfillDB([h_local, h_intl, h_sec])

    result = await hs.backfill_helper_phone_formats(db)

    assert h_local.phone == "989129484023"                 # converted
    assert h_intl.phone == "989121015426"                  # already intl → unchanged
    assert h_sec.phone == "989101764710"                   # primary converted
    assert h_sec.phone_secondary == "989129373764"         # secondary converted
    assert result["total"] == 3
    assert result["changed"] == 3                          # h_local(1) + h_sec primary+secondary(2)
    assert db.commits == 1


@pytest.mark.asyncio
async def test_backfill_is_idempotent_second_run_changes_nothing():
    h = _helper("x", "09129484023")
    db = _BackfillDB([h])
    await hs.backfill_helper_phone_formats(db)
    result2 = await hs.backfill_helper_phone_formats(db)
    assert result2["changed"] == 0
    assert h.phone == "989129484023"


# ── end-to-end: a 09-stored contact matches a 98-format incoming → task done ──
class _IncomingDB:
    """Minimal router for handle_helper_incoming's completion path. Accounts empty → no sender →
    the thank-you send is skipped, isolating the match+`done` transition (the fix under test)."""
    def __init__(self, helper, task):
        self._helper = helper
        self._task = task
        self.added = []
    def _sql(self, q):
        try: return str(q.compile(compile_kwargs={"literal_binds": True})).lower()
        except Exception: return str(q).lower()
    async def execute(self, q):
        sql = self._sql(q)
        if "warmup_team_enrollment" in sql:
            return _Scal([])                     # get_team_enrollment → None → no escalation
        if "warmup_helper_thread" in sql:
            return _Scal([])                     # no existing thread → created via db.add
        if "warmup_helper_task" in sql:
            rows = [self._task] if self._task.status in sql else []
            if "cold_instance_id =" in sql:
                rows = [t for t in rows if t.cold_instance_id.lower() in sql]
            return _Scal(rows)
        if "warmup_enrollment" in sql:
            return _Rows([])                     # _enrollment_states
        if "warmup_helper" in sql:               # the phone.in_(forms) match
            # match only when one of the contact's ACTUAL stored numbers appears among the
            # incoming's forms (i.e. is present as a literal in the compiled IN (...) clause)
            stored = [p for p in (self._helper.phone, self._helper.phone_secondary) if p]
            return _Scal([self._helper] if any(p in sql for p in stored) else [])
        if "accounts" in sql:
            return _Scal([])                     # no active senders → thank-you skipped
        return _Scal([])
    def add(self, o): self.added.append(o)
    async def flush(self): pass
    async def commit(self): pass
    async def refresh(self, o): pass
    async def get(self, model, pk):
        return self._helper if getattr(self._helper, "id", None) == pk else None


class _Scal:
    def __init__(self, rows): self._r = rows
    def scalars(self):
        outer = self
        class _S:
            def all(s): return list(outer._r)
        return _S()
    def scalar_one_or_none(self): return self._r[0] if self._r else None


class _Rows:
    def __init__(self, rows): self._r = rows
    def all(self): return list(self._r)


@pytest.mark.asyncio
async def test_incoming_matches_local_stored_contact_and_completes():
    # Contact stored LOCAL (09…) — exactly the format that was silently missed before the fix.
    helper = WarmupHelper(name="پروین رضایی", phone="09129484023",
                          phone_secondary=None, is_active=True, sender_instance_id="P1")
    helper.id = uuid.uuid4()
    task = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C1", status=hs.STATUS_REMINDED)
    task.id = uuid.uuid4()
    db = _IncomingDB(helper, task)

    # Incoming arrives INTERNATIONAL (as every WhatsApp chatId does).
    res = await he.handle_helper_incoming(db, "C1", "989129484023@c.us",
                                          now=datetime(2026, 5, 4, 11, 0), message_text=None)

    assert res is not None                         # contact matched (was None before the fix)
    assert task.status == hs.STATUS_DONE           # task retroactively completes
    assert task.done_at is not None


@pytest.mark.asyncio
async def test_incoming_unknown_number_still_no_match():
    helper = WarmupHelper(name="x", phone="09129484023", is_active=True, sender_instance_id="P1")
    helper.id = uuid.uuid4()
    task = WarmupHelperTask(helper_id=helper.id, cold_instance_id="C1", status=hs.STATUS_ASKED)
    task.id = uuid.uuid4()
    db = _IncomingDB(helper, task)
    res = await he.handle_helper_incoming(db, "C1", "989999999999",
                                          now=datetime(2026, 5, 4, 11, 0), message_text=None)
    assert res is None                             # a genuinely different number does NOT match
    assert task.status == hs.STATUS_ASKED
