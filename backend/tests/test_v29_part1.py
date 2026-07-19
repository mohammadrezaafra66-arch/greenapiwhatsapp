"""V29 PART 1 «همکاری تیمی» — extend warmup_helper with the rich personnel profile,
full-name-mandatory (at the V29 boundary), per-sender toggle, is_current brief, and the
real DB-level UNIQUE(helper_id, cold_instance_id).

Proves:
  • the rich-profile columns (job_title/years_experience/personal_benefit_note/phone_secondary)
    save + normalize correctly;
  • full-name enforcement rejects a single-token name ONLY when require_full_name=True (the V29
    API path), so the V25/V28 service contract stays intact;
  • the per-sender toggle defaults ON, flips independently of the global one;
  • outreach_brief.is_current tracks exactly one current brief per sender;
  • the WarmupHelperTask model declares the (helper, cold) unique constraint;
  • existing V25/V28 behavior is unchanged.
"""
import uuid
import pytest

from app.services import warmup_helper_service as hs
from app.models.warmup_helpers import (
    WarmupHelper, WarmupHelperTask, WarmupHelperConfig, OutreachBrief, WarmupSenderConfig,
)


# ── staged-result fake session (mirrors the V28 test harness) ────────────────
class _Scalars:
    def __init__(self, items): self._items = list(items)
    def all(self): return list(self._items)
    def first(self): return self._items[0] if self._items else None


class _Result:
    def __init__(self, scalars=None, scalar=None, rows=None):
        self._scalars = list(scalars) if scalars is not None else []
        self._scalar = scalar
        self._rows = rows
    def scalars(self): return _Scalars(self._scalars)
    def scalar(self): return self._scalar
    def all(self): return list(self._rows) if self._rows is not None else list(self._scalars)
    def scalar_one_or_none(self): return self._scalars[0] if self._scalars else None


class _DB:
    def __init__(self, results=None):
        self._results = list(results or [])
        self.added = []
        self.commits = 0
        self.executed = []
    async def execute(self, *a, **k):
        self.executed.append((a, k))
        return self._results.pop(0) if self._results else _Result()
    def add(self, o): self.added.append(o)
    async def flush(self): pass
    async def commit(self): self.commits += 1
    async def refresh(self, o): pass
    async def get(self, model, pk): return None


# ── full-name helper (pure) ──────────────────────────────────────────────────
def test_is_full_name_pure():
    assert hs.is_full_name("رضا محمدی") is True
    assert hs.is_full_name("  علی   کریمی  ") is True     # collapses whitespace
    assert hs.is_full_name("رضا") is False                # single token
    assert hs.is_full_name("") is False
    assert hs.is_full_name(None) is False


# ── require_full_name gate ────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_add_helper_full_name_required_only_when_flagged():
    # V29 API path: single token rejected
    with pytest.raises(ValueError):
        await hs.add_helper(_DB(), "رضا", "989120000001", sender_instance_id="S1",
                            require_full_name=True)
    # legacy/service path (default): single token still allowed (V28 contract preserved)
    h = await hs.add_helper(_DB(), "رضا", "989120000001", sender_instance_id="S1")
    assert h.name == "رضا"


@pytest.mark.asyncio
async def test_add_helper_full_name_accepts_first_last():
    h = await hs.add_helper(_DB(), "رضا محمدی", "+98 912 000 0001", sender_instance_id="S1",
                            require_full_name=True)
    assert h.name == "رضا محمدی" and h.phone == "989120000001"


# ── rich profile columns ──────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_add_helper_saves_rich_profile():
    h = await hs.add_helper(
        _DB(), "سارا احمدی", "989120000002", sender_instance_id="S1",
        job_title="کارشناس فروش", years_experience="۵",
        personal_benefit_note="تخفیف پرسنلی", phone_secondary="+98 913 111 2222",
    )
    assert h.job_title == "کارشناس فروش"
    assert h.years_experience == 5                      # Persian digit coerced
    assert h.personal_benefit_note == "تخفیف پرسنلی"
    assert h.phone_secondary == "989131112222"          # normalized to digits


@pytest.mark.asyncio
async def test_add_helper_blank_profile_stays_none():
    h = await hs.add_helper(_DB(), "نیما تهرانی", "989120000003", sender_instance_id="S1",
                            job_title="  ", years_experience="", personal_benefit_note=None,
                            phone_secondary="")
    assert h.job_title is None and h.years_experience is None
    assert h.personal_benefit_note is None and h.phone_secondary is None


def test_coerce_years():
    assert hs._coerce_years("3") == 3
    assert hs._coerce_years(7) == 7
    assert hs._coerce_years("۱۲") == 12
    assert hs._coerce_years("") is None
    assert hs._coerce_years(None) is None
    assert hs._coerce_years("abc") is None
    assert hs._coerce_years(-4) is None


@pytest.mark.asyncio
async def test_update_helper_patches_profile_fields():
    existing = WarmupHelper(name="رضا محمدی", phone="989120000001", sender_instance_id="S1",
                            job_title="قدیمی", years_experience=1)
    existing.id = uuid.uuid4()
    class _DBg(_DB):
        async def get(self, model, pk): return existing
    db = _DBg()
    out = await hs.update_helper(db, existing.id, job_title="جدید", years_experience=9)
    assert out.job_title == "جدید" and out.years_experience == 9
    # omitted fields untouched
    assert out.name == "رضا محمدی"
    # clearing with empty string
    out2 = await hs.update_helper(db, existing.id, job_title="")
    assert out2.job_title is None


# ── per-sender toggle ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_sender_config_defaults_on_and_flips():
    # lazily-created config defaults ON
    db = _DB(results=[_Result(scalars=[])])
    cfg = await hs.get_sender_config(db, "S1")
    assert cfg.is_enabled is True and cfg.sender_instance_id == "S1"

    existing = WarmupSenderConfig(sender_instance_id="S1", is_enabled=True)
    db2 = _DB(results=[_Result(scalars=[existing])])
    out = await hs.set_sender_enabled(db2, "S1", False)
    assert out.is_enabled is False and db2.commits >= 1


@pytest.mark.asyncio
async def test_is_sender_enabled_absent_defaults_true():
    db = _DB(results=[_Result(scalars=[])])
    assert await hs.is_sender_enabled(db, "S1") is True
    # explicit disabled
    dis = WarmupSenderConfig(sender_instance_id="S2", is_enabled=False)
    db2 = _DB(results=[_Result(scalars=[dis])])
    assert await hs.is_sender_enabled(db2, "S2") is False
    # None sender → governed by the global toggle → treated enabled here
    assert await hs.is_sender_enabled(_DB(), None) is True


# ── is_current brief ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_set_current_brief_marks_one_current():
    db = _DB()
    b = await hs.set_current_brief(db, "S1", "  به شماره‌های جدید سلام بده  ")
    assert b.is_current is True
    assert b.brief_text == "به شماره‌های جدید سلام بده"    # stripped
    assert db.commits >= 1
    # it ran an UPDATE (clear others) before adding the new current brief
    assert len(db.executed) >= 1
    assert any(isinstance(o, OutreachBrief) and o.is_current for o in db.added)


@pytest.mark.asyncio
async def test_get_current_brief_prefers_current_then_latest():
    cur = OutreachBrief(sender_instance_id="S1", brief_text="فعلی", is_current=True)
    db = _DB(results=[_Result(scalars=[cur])])
    assert (await hs.get_current_brief(db, "S1")) is cur

    # no current flagged → fall back to latest
    latest = OutreachBrief(sender_instance_id="S1", brief_text="آخری", is_current=False)
    db2 = _DB(results=[_Result(scalars=[]), _Result(scalars=[latest])])
    assert (await hs.get_current_brief(db2, "S1")) is latest


# ── unique constraint declared on the model ──────────────────────────────────
def test_task_model_declares_unique_pair():
    cons = {c.name for c in WarmupHelperTask.__table__.constraints}
    assert "uq_warmup_helper_task_pair" in cons


def test_sender_config_model_shape():
    c = WarmupSenderConfig(sender_instance_id="S9", is_enabled=False)
    assert c.sender_instance_id == "S9" and c.is_enabled is False
