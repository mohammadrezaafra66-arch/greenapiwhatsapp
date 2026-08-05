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
    """Phase 6 eligibility must not introduce its own DDL; plan snapshots suffice.

    Phase 7 may add `v67_07_fleet_shadow_snapshots` — that is out of Phase 6 scope.
    """
    versions = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    phase6_named = list(versions.glob("*phase6*eligib*")) + list(versions.glob("*v67_06*eligib*"))
    assert phase6_named == [], f"unexpected Phase 6 eligibility migrations: {phase6_named}"
    # Phase 6 head at ship time was v67_06; later phases may advance head.
    assert any("v67_06" in p.name for p in versions.glob("*.py"))


def test_phase5_plan_table_migration_still_present():
    versions = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    assert any("v67_06" in p.name for p in versions.glob("*.py"))
