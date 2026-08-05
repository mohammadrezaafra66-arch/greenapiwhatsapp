"""V67 Phase 5 — capacity / budget / campaign / schedule / optimizer unit tests."""
from __future__ import annotations
import inspect
from datetime import datetime

from app.services.capacity_planner import CapacityPlanner
from app.services.fleet_budget import FleetBudgetEngine
from app.services.campaign_planner import CampaignPlanner
from app.services.schedule_planner import SchedulePlanner
from app.services.fleet_optimizer import FleetOptimizer
from app.services.fleet_policy_defaults import CONSERVATIVE_POLICY_SETTINGS
from app.services import send_gate

POL = {"settings_json": dict(CONSERVATIVE_POLICY_SETTINGS)}
NOW = datetime(2026, 8, 5, 12, 0, 0)


def test_capacity_deterministic():
    p = CapacityPlanner()
    a = p.evaluate(
        fleet_state="CAMPAIGN_READY", policy=POL,
        evidence={"ramp_day_index": 6, "active_days": 20},
        trust_score=80, risk_level="NORMAL",
    )
    b = p.evaluate(
        fleet_state="CAMPAIGN_READY", policy=POL,
        evidence={"ramp_day_index": 6, "active_days": 20},
        trust_score=80, risk_level="NORMAL",
    )
    assert a == b
    assert a.daily_capacity > 0
    assert a.mutates_runtime is False
    assert a.simulation_only is True


def test_capacity_risk_and_state_zero():
    p = CapacityPlanner()
    zero = p.evaluate(fleet_state="SUSPENDED", policy=POL, evidence={}, trust_score=90, risk_level="NORMAL")
    assert zero.daily_capacity == 0
    crit = p.evaluate(
        fleet_state="CAMPAIGN_READY", policy=POL, evidence={"ramp_day_index": 6},
        trust_score=90, risk_level="CRITICAL",
    )
    assert crit.daily_capacity == 0
    warm = p.evaluate(
        fleet_state="WARMUP_READY", policy=POL, evidence={"ramp_day_index": 6},
        trust_score=80, risk_level="NORMAL",
    )
    assert warm.campaign_budget == 0  # not campaign-capable yet


def test_budget_deterministic_and_reserve():
    e = FleetBudgetEngine()
    a = e.compute(daily_capacity=100, used_today=20, reserve_ratio=0.15, policy=POL)
    b = e.compute(daily_capacity=100, used_today=20, reserve_ratio=0.15, policy=POL)
    assert a == b
    assert a.safety_reserve == 15
    assert a.remaining_budget == 80
    assert a.recommended_usage == 65
    assert a.mutates_runtime is False


def test_schedule_deterministic_jitter():
    s = SchedulePlanner()
    a = s.preview(now=NOW, policy=POL, account_id="acc-1", batch_count=2, spacing_minutes=30)
    b = s.preview(now=NOW, policy=POL, account_id="acc-1", batch_count=2, spacing_minutes=30)
    assert a == b
    assert a.executes is False
    assert len(a.slots) == 2


def test_optimizer_buckets():
    o = FleetOptimizer().recommend([
        {"account_id": "1", "fleet_state": "CAMPAIGN_READY", "trust_score": 70, "risk_level": "NORMAL"},
        {"account_id": "2", "fleet_state": "REWARM_REQUIRED", "trust_score": 10, "risk_level": "HIGH"},
        {"account_id": "3", "fleet_state": "MAINTENANCE", "trust_score": 60, "risk_level": "NORMAL"},
        {"account_id": "4", "fleet_state": "AT_RISK", "trust_score": 40, "risk_level": "MEDIUM"},
        {"account_id": "5", "fleet_state": "WARMUP_READY", "trust_score": 50, "risk_level": "LOW"},
    ])
    assert "1" in o.best_accounts
    assert "2" in o.rewarm_accounts
    assert "3" in o.maintenance_accounts
    assert "4" in o.cooldown_accounts
    assert "5" in o.rest_accounts
    assert o.mutates_accounts is False


def test_campaign_planner_simulation_only():
    cp = CampaignPlanner()
    accounts = [
        {"account_id": "a1", "fleet_state": "CAMPAIGN_READY", "trust_score": 80,
         "risk_level": "NORMAL", "used_today": 0, "evidence": {"ramp_day_index": 6}},
        {"account_id": "a2", "fleet_state": "SUSPENDED", "trust_score": 10,
         "risk_level": "CRITICAL", "used_today": 0, "evidence": {}},
    ]
    p1 = cp.plan(campaign={"target_messages": 50, "batch_size": 10, "spacing_minutes": 15},
                 accounts=accounts, policy=POL, now=NOW)
    p2 = cp.plan(campaign={"target_messages": 50, "batch_size": 10, "spacing_minutes": 15},
                 accounts=accounts, policy=POL, now=NOW)
    assert p1 == p2
    assert p1.executes_campaign is False
    assert p1.mutates_runtime is False
    assert "a1" in p1.recommended_accounts
    assert "a2" not in p1.recommended_accounts
    for batch in p1.recommended_batches:
        assert batch["status"] == "SIMULATED_ONLY"


def test_trust_weighting_affects_capacity():
    p = CapacityPlanner()
    hi = p.evaluate(fleet_state="CAMPAIGN_READY", policy=POL,
                    evidence={"ramp_day_index": 6}, trust_score=100, risk_level="NORMAL")
    lo = p.evaluate(fleet_state="CAMPAIGN_READY", policy=POL,
                    evidence={"ramp_day_index": 6}, trust_score=25, risk_level="NORMAL")
    assert hi.daily_capacity > lo.daily_capacity


def test_send_gate_untouched_no_phase6_leak():
    src = inspect.getsource(send_gate)
    assert "CapacityPlanner" not in src
    assert "CampaignPlanner" not in src
    assert "FleetBudgetEngine" not in src
    assert "fleet_planning" not in src
    assert "Autopilot" not in src
