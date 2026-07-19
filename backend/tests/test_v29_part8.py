"""V29 PART 8 «همکاری تیمی» — sender warmth score/analysis.

Proves:
  • the score reflects age (saturating at 14 days), incident history (any incident zeroes the
    clean-history component), and recent activity;
  • the level maps کم/متوسط/بالا at the right thresholds;
  • a sender that FAILS V27's binary gate is never «بالا»;
  • the async wrapper composes age + incidents + activity from loaded rows.
"""
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

from app.services import warmup_warmth as ww
from app.models.warmup_mesh import WarmupEnrollment

NOW = datetime(2026, 5, 4, 11, 0)


# ── pure compute_warmth ───────────────────────────────────────────────────────
def test_fresh_clean_account_is_low_to_mid():
    # 0 days old, clean, no activity → age 0 + incident 30 + activity 0 = 30 → کم
    out = ww.compute_warmth(age_days=0, recent_incident_count=0, days_since_activity=None,
                            eligible=False)
    assert out["score"] == 30 and out["level"] == ww.LEVEL_LOW_FA


def test_established_clean_active_is_high():
    out = ww.compute_warmth(age_days=20, recent_incident_count=0, days_since_activity=1,
                            eligible=True)
    assert out["components"] == {"age": 50, "incident_free": 30, "activity": 20}
    assert out["score"] == 100 and out["level"] == ww.LEVEL_HIGH_FA


def test_incident_zeroes_clean_component_and_caps_below_high():
    # 20 days old + recent incident + active → 50 + 0 + 20 = 70, but NOT eligible → capped < 70
    out = ww.compute_warmth(age_days=20, recent_incident_count=1, days_since_activity=1,
                            eligible=False)
    assert out["components"]["incident_free"] == 0
    assert out["score"] < ww.LEVEL_HIGH_MIN and out["level"] != ww.LEVEL_HIGH_FA


def test_age_saturates_at_14_days():
    assert ww._age_score(14) == 50
    assert ww._age_score(7) == 25
    assert ww._age_score(100) == 50           # saturates
    assert ww._age_score(0) == 0
    assert ww._age_score(None) == 0


def test_activity_windows():
    assert ww._activity_score(1) == 20
    assert ww._activity_score(10) == 10
    assert ww._activity_score(30) == 0
    assert ww._activity_score(None) == 0


def test_level_thresholds():
    assert ww.level_for_score(70) == ww.LEVEL_HIGH_FA
    assert ww.level_for_score(69) == ww.LEVEL_MID_FA
    assert ww.level_for_score(40) == ww.LEVEL_MID_FA
    assert ww.level_for_score(39) == ww.LEVEL_LOW_FA


# ── async wrapper ─────────────────────────────────────────────────────────────
class _Res:
    def __init__(self, scalars=None, scalar=None):
        self._s = scalars or []; self._scalar = scalar
    def scalars(self):
        outer = self
        class _S:
            def all(s): return list(outer._s)
        return _S()
    def scalar(self): return self._scalar
    def scalar_one_or_none(self): return self._s[0] if self._s else None


class _DB:
    def __init__(self, enr, incident_count):
        self.enr = enr; self.incident_count = incident_count
    async def execute(self, q):
        sql = str(q).lower()
        if "count(" in sql:
            return _Res(scalar=self.incident_count)
        if "warmup_enrollment" in sql:
            return _Res(scalars=[self.enr] if self.enr else [])
        return _Res()


@pytest.mark.asyncio
async def test_warmth_for_account_established_clean():
    acc = SimpleNamespace(instance_id="P1", name="peer-1", id=uuid.uuid4())
    enr = WarmupEnrollment(instance_id="P1", authorized_at=NOW - timedelta(days=20),
                           last_activity_at=NOW - timedelta(days=1))
    out = await ww.warmth_for_account(_DB(enr, 0), acc, NOW)
    assert out["level"] == ww.LEVEL_HIGH_FA and out["eligible"] is True
    assert out["age_days"] == 20.0 and out["recent_incidents"] == 0


@pytest.mark.asyncio
async def test_warmth_for_account_young_is_not_high():
    acc = SimpleNamespace(instance_id="P2", name="peer-2", id=uuid.uuid4())
    enr = WarmupEnrollment(instance_id="P2", authorized_at=NOW - timedelta(days=3),
                           last_activity_at=NOW - timedelta(days=1))
    out = await ww.warmth_for_account(_DB(enr, 0), acc, NOW)
    assert out["eligible"] is False and out["level"] != ww.LEVEL_HIGH_FA
