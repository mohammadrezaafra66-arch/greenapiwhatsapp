"""V39 PART 2 — hard Team-Collaboration sender-eligibility gate at assignment, with logged override.

Proves:
  • the eligibility check REUSES V27's ≥14-day + clean-history computation and reports the EXACT
    Persian reason (precise day count for too-young; a distinct message for a recent incident);
  • enforce_for_assignment: an ELIGIBLE sender passes with no override; an INELIGIBLE sender with no
    override RAISES a specific Persian error; an ineligible sender WITH an override + note succeeds,
    PERSISTS the override on warmup_sender_config, and writes an auditable log entry; an override
    WITHOUT a note is rejected;
  • a prior standing override lets later assignments through; and the persisted model carries the
    who/when/why fields.
"""
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

from app.services import sender_eligibility as se
from app.services import warmup_helper_log as tclog
from app.models.warmup_mesh import WarmupEnrollment
from app.models.warmup_helpers import WarmupSenderConfig
from app.services.warmup_peer_eligibility import MIN_PEER_AGE_DAYS

NOW = datetime(2026, 7, 22, 12, 0, 0)

# Captured before conftest's autouse fixture stubs it to always-allow, so the send-time tests below
# exercise the real decision.
_REAL_SENDER_SEND_ALLOWED = se.sender_send_allowed


@pytest.fixture(autouse=True)
def _use_real_eligibility(monkeypatch):
    monkeypatch.setattr("app.services.sender_eligibility.sender_send_allowed",
                        _REAL_SENDER_SEND_ALLOWED)
    yield


# ── fake session (SQL-string routing, mirrors test_v29_part8's _DB) ───────────
class _Res:
    def __init__(self, scalars=None, scalar=None):
        self._s = scalars or []
        self._scalar = scalar
    def scalars(self):
        outer = self
        class _S:
            def all(s): return list(outer._s)
        return _S()
    def scalar(self): return self._scalar
    def scalar_one_or_none(self): return self._s[0] if self._s else None


class _DB:
    def __init__(self, account=None, enr=None, incident_count=0, cfg=None):
        self.account = account
        self.enr = enr
        self.incident_count = incident_count
        self.cfg = cfg
        self.added = []
        self.commits = 0
    async def execute(self, q):
        sql = str(q).lower()
        if "count(" in sql:
            return _Res(scalar=self.incident_count)
        if "warmup_enrollment" in sql:
            return _Res(scalars=[self.enr] if self.enr else [])
        if "warmup_sender_config" in sql:
            return _Res(scalars=[self.cfg] if self.cfg else [])
        if "accounts" in sql:
            return _Res(scalars=[self.account] if self.account else [])
        return _Res()
    def add(self, x):
        self.added.append(x)
        if isinstance(x, WarmupSenderConfig):
            self.cfg = x
    async def flush(self): pass
    async def commit(self): self.commits += 1


def _acc(iid="S1"):
    # created_at/partner_created_at left None so the enrollment's authorized_at drives peer_age_days
    # (connected_since takes the EARLIEST anchor — an old created_at would mask a young enrollment).
    return SimpleNamespace(instance_id=iid, name="فرستنده", id=uuid.uuid4(),
                           partner_created_at=None, created_at=None)


def _enr(days_old):
    return WarmupEnrollment(instance_id="S1", authorized_at=NOW - timedelta(days=days_old),
                            last_activity_at=NOW - timedelta(days=1))


# ── precise Persian messages ─────────────────────────────────────────────────
def test_too_young_message_has_exact_days_in_persian():
    msg = se.too_young_message_fa(6.9)
    assert "۶.۹ روز" in msg and "۱۴ روز" in msg


def test_recent_incident_message_is_distinct():
    assert "حادثه" in se.RECENT_INCIDENT_MESSAGE_FA


# ── check_sender_eligibility ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_eligible_established_clean_sender():
    db = _DB(account=_acc(), enr=_enr(20), incident_count=0)
    eligible, reason, msg, age = await se.check_sender_eligibility(db, "S1", NOW)
    assert eligible is True and reason == "ok" and msg is None
    assert age == pytest.approx(20.0)


@pytest.mark.asyncio
async def test_too_young_sender_reports_exact_days():
    db = _DB(account=_acc(), enr=_enr(6.9), incident_count=0)
    eligible, reason, msg, age = await se.check_sender_eligibility(db, "S1", NOW)
    assert eligible is False and reason == "too_young"
    assert "۶.۹ روز" in msg and age == pytest.approx(6.9)


@pytest.mark.asyncio
async def test_recent_incident_sender_blocked():
    db = _DB(account=_acc(), enr=_enr(20), incident_count=1)
    eligible, reason, msg, age = await se.check_sender_eligibility(db, "S1", NOW)
    assert eligible is False and reason == "recent_incident"
    assert "حادثه" in msg


@pytest.mark.asyncio
async def test_unknown_sender_is_not_found():
    db = _DB(account=None)
    eligible, reason, msg, age = await se.check_sender_eligibility(db, "NOPE", NOW)
    assert eligible is False and reason == "not_found" and age is None


# ── enforce_for_assignment ───────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_enforce_allows_eligible_without_override():
    db = _DB(account=_acc(), enr=_enr(20), incident_count=0)
    await se.enforce_for_assignment(db, "S1", now=NOW)     # no raise
    assert not any(isinstance(x, WarmupSenderConfig) for x in db.added)   # nothing persisted


@pytest.mark.asyncio
async def test_enforce_rejects_ineligible_without_override():
    db = _DB(account=_acc(), enr=_enr(6.9), incident_count=0)
    with pytest.raises(ValueError) as ei:
        await se.enforce_for_assignment(db, "S1", now=NOW)
    assert "۶.۹ روز" in str(ei.value)


@pytest.mark.asyncio
async def test_enforce_override_without_note_is_rejected():
    db = _DB(account=_acc(), enr=_enr(6.9), incident_count=0)
    with pytest.raises(ValueError) as ei:
        await se.enforce_for_assignment(db, "S1", override=True, note="   ", now=NOW)
    assert str(ei.value) == se.NOTE_REQUIRED_FA


@pytest.mark.asyncio
async def test_enforce_override_with_note_persists_and_audits():
    db = _DB(account=_acc(), enr=_enr(6.9), incident_count=0)
    await se.enforce_for_assignment(db, "S1", override=True,
                                    note="کمبود اکانت سالم؛ ریسک پذیرفته شد", now=NOW)
    cfgs = [x for x in db.added if isinstance(x, WarmupSenderConfig)]
    assert len(cfgs) == 1
    cfg = cfgs[0]
    assert cfg.eligibility_overridden_at == NOW
    assert "ریسک" in cfg.eligibility_override_note
    assert cfg.eligibility_overridden_by == se.DEFAULT_OVERRIDER
    # an auditable log row was written with the override event type
    logs = [x for x in db.added if x.__class__.__name__ == "WarmupHelperLog"]
    assert len(logs) == 1 and logs[0].event_type == tclog.EVENT_ELIGIBILITY_OVERRIDE
    assert logs[0].sender_instance_id == "S1"


@pytest.mark.asyncio
async def test_prior_override_lets_later_assignment_through():
    prior = WarmupSenderConfig(sender_instance_id="S1", is_enabled=True,
                               eligibility_overridden_at=NOW - timedelta(days=1),
                               eligibility_override_note="قبلاً تأیید شد",
                               eligibility_overridden_by="admin")
    db = _DB(account=_acc(), enr=_enr(6.9), incident_count=0, cfg=prior)
    # ineligible + no override flag in THIS request, but a standing override exists → no raise
    await se.enforce_for_assignment(db, "S1", now=NOW)


@pytest.mark.asyncio
async def test_none_sender_is_not_gated():
    db = _DB()
    await se.enforce_for_assignment(db, None, now=NOW)     # no raise, no lookups needed


# ── PART 3 preview: sender_send_allowed (fully exercised in test_v39_part3) ───
@pytest.mark.asyncio
async def test_send_allowed_for_eligible_and_overridden():
    assert (await se.sender_send_allowed(_DB(account=_acc(), enr=_enr(20)), "S1", NOW)) == (True, "ok")
    prior = WarmupSenderConfig(sender_instance_id="S1",
                               eligibility_overridden_at=NOW - timedelta(days=1))
    db = _DB(account=_acc(), enr=_enr(6.9), cfg=prior)
    assert (await se.sender_send_allowed(db, "S1", NOW)) == (True, "overridden")


@pytest.mark.asyncio
async def test_model_carries_override_columns():
    cfg = WarmupSenderConfig(sender_instance_id="Z", eligibility_overridden_at=NOW,
                             eligibility_override_note="n", eligibility_overridden_by="admin")
    assert cfg.eligibility_overridden_at == NOW
    assert se.override_active(cfg) is True
    assert se.override_active(WarmupSenderConfig(sender_instance_id="Q")) is False
