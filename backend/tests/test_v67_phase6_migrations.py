"""V67 Phase 6 — no new DDL; eligibility snapshots reuse fleet_plan_snapshots."""
from __future__ import annotations
from pathlib import Path

from app.models.fleet_plan import FleetPlanSnapshot


def test_eligibility_reuses_plan_snapshot_model():
    cols = {c.name for c in FleetPlanSnapshot.__table__.columns}
    assert "plan_type" in cols
    assert "payload_json" in cols
    assert "simulation_only" in cols


def test_no_phase6_alembic_revision_required():
    """Phase 6 must not introduce a new migration; v67_06 is sufficient."""
    versions = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    phase6 = list(versions.glob("*v67_07*")) + list(versions.glob("*phase6*eligib*"))
    assert phase6 == [], f"unexpected Phase 6 migrations: {phase6}"


def test_phase5_plan_table_migration_still_present():
    versions = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    assert any("v67_06" in p.name for p in versions.glob("*.py"))
