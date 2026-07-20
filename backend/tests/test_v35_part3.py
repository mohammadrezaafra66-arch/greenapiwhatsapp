"""V35 PART 3 — contact relationship category + optional referral note.

Adds two nullable, independent fields to warmup_helper (contact):
  • `relationship` — one of friend/colleague/employee/family (stored as an English code; the UI
    shows the Persian label). Any other value coerces to None.
  • `referral_note` — free text (e.g. «شماره شما را آقای X داده») woven into the AI ask-message
    generator alongside the existing job_title / years_experience / personal_benefit_note context.

Proves: saving persists the fields; the referral note (and relationship) reach the AI prompt's
profile_line; omitting the note is a no-op that keeps existing generation unchanged.
"""
import random
import pytest

from app.services import warmup_helper_service as hs
from app.services import outreach_message as om
from app.models.warmup_helpers import WarmupHelper


# ── fake session (mirrors the V29 harness: add_helper only builds the Python object) ──
class _DB:
    def __init__(self): self.added = []; self.commits = 0
    async def execute(self, *a, **k):
        class _R:
            def scalars(self_):  # noqa
                class _S:
                    def all(self__): return []
                    def first(self__): return None
                return _S()
        return _R()
    def add(self, o): self.added.append(o)
    async def flush(self): pass
    async def commit(self): self.commits += 1
    async def refresh(self, o): pass
    async def get(self, model, pk): return getattr(self, "_row", None)


# ── model column presence ─────────────────────────────────────────────────────
def test_model_has_new_columns():
    cols = WarmupHelper.__table__.columns.keys()
    assert "relationship" in cols
    assert "referral_note" in cols


# ── relationship coercion ─────────────────────────────────────────────────────
def test_coerce_relationship_valid_and_invalid():
    assert hs._coerce_relationship("friend") == "friend"
    assert hs._coerce_relationship("Colleague") == "colleague"   # normalized lower
    assert hs._coerce_relationship("employee") == "employee"
    assert hs._coerce_relationship("family") == "family"
    assert hs._coerce_relationship("boss") is None               # not in the allowed set
    assert hs._coerce_relationship("") is None
    assert hs._coerce_relationship(None) is None


# ── add_helper persists the new fields ────────────────────────────────────────
@pytest.mark.asyncio
async def test_add_helper_saves_relationship_and_referral_note():
    h = await hs.add_helper(
        _DB(), "رضا محمدی", "989120000010", sender_instance_id="S1",
        relationship="colleague", referral_note="شماره شما را آقای کریمی داده",
    )
    assert h.relationship == "colleague"
    assert h.referral_note == "شماره شما را آقای کریمی داده"


@pytest.mark.asyncio
async def test_add_helper_invalid_relationship_becomes_none():
    h = await hs.add_helper(_DB(), "سارا احمدی", "989120000011", sender_instance_id="S1",
                            relationship="bestie", referral_note="   ")
    assert h.relationship is None
    assert h.referral_note is None          # whitespace-only note stays None


@pytest.mark.asyncio
async def test_add_helper_defaults_when_omitted():
    h = await hs.add_helper(_DB(), "نیما تهرانی", "989120000012", sender_instance_id="S1")
    assert h.relationship is None and h.referral_note is None


# ── update_helper patches independently (sentinel-based) ──────────────────────
@pytest.mark.asyncio
async def test_update_helper_patches_relationship_and_note():
    db = _DB()
    existing = WarmupHelper(name="رضا محمدی", phone="989120000013", sender_instance_id="S1")
    db._row = existing
    h = await hs.update_helper(db, existing.id if getattr(existing, "id", None) else "x",
                               relationship="employee", referral_note="از طریق نمایشگاه آشنا شدیم")
    assert h.relationship == "employee"
    assert h.referral_note == "از طریق نمایشگاه آشنا شدیم"


@pytest.mark.asyncio
async def test_update_helper_omitting_fields_leaves_unchanged():
    db = _DB()
    existing = WarmupHelper(name="رضا محمدی", phone="989120000014", sender_instance_id="S1",
                            relationship="friend", referral_note="قبلاً ثبت شده")
    db._row = existing
    h = await hs.update_helper(db, "x", name="رضا محمدی نو")   # only name patched
    assert h.relationship == "friend"                          # untouched
    assert h.referral_note == "قبلاً ثبت شده"


# ── the referral note + relationship reach the AI prompt ──────────────────────
CONTACT_WITH_REFERRAL = {
    "name": "رضا محمدی", "job_title": "کارشناس فروش", "years_experience": 6,
    "personal_benefit_note": "تخفیف پرسنلی", "relationship": "colleague",
    "referral_note": "شماره شما را آقای کریمی داده",
}


def test_profile_line_includes_referral_note_and_relationship():
    line = om._profile_line(
        job_title="کارشناس فروش", years_experience=6, personal_benefit_note="تخفیف پرسنلی",
        relationship="colleague", referral_note="شماره شما را آقای کریمی داده")
    assert "شماره شما را آقای کریمی داده" in line
    assert "همکار" in line                    # Persian label for colleague


@pytest.mark.asyncio
async def test_referral_note_reaches_ai_prompt():
    seen = {}
    async def ai(*, name, topic, step_count, brief, profile_line):
        seen["profile_line"] = profile_line
        return f"سلام {name}، درباره‌ی {topic} یه لطف کوچیک داشتم"
    msg, source = await om.generate_thread_ask_message(
        brief="سلام بده", contact=CONTACT_WITH_REFERRAL, topic="پیگیری سفارش تلویزیون",
        step_count=0, cold_phone_digits=["989120000001"], ai_fn=ai, rng=random.Random(1))
    assert source == "ai"
    assert "شماره شما را آقای کریمی داده" in seen["profile_line"]   # referral note passed through
    assert "همکار" in seen["profile_line"]                          # relationship passed through


@pytest.mark.asyncio
async def test_omitting_referral_note_keeps_generation_unchanged():
    """A contact WITHOUT a referral note (the pre-V35 shape) generates as before — the profile
    line carries only the legacy job/experience/benefit context, no referral clause."""
    seen = {}
    async def ai(*, name, topic, step_count, brief, profile_line):
        seen["profile_line"] = profile_line
        return f"سلام {name}، درباره‌ی {topic} یه لطف کوچیک داشتم"
    legacy = {"name": "رضا محمدی", "job_title": "کارشناس فروش", "years_experience": 6,
              "personal_benefit_note": "تخفیف پرسنلی"}
    msg, source = await om.generate_thread_ask_message(
        brief="سلام بده", contact=legacy, topic="پیگیری سفارش تلویزیون",
        step_count=0, cold_phone_digits=["989120000001"], ai_fn=ai, rng=random.Random(1))
    assert source == "ai" and "رضا محمدی" in msg
    assert "کارشناس فروش" in seen["profile_line"]
    assert "معرف" not in seen["profile_line"] and "نسبت او" not in seen["profile_line"]
