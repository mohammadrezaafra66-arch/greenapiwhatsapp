"""Scope isolation: no frontend/API/migration/write side effects in Phase A modules."""
from __future__ import annotations
import inspect
from pathlib import Path

from app.scripts import fleet_shadow_daily_report as cli
from app.services.daily_observation import service as svc_mod
from app.services.daily_observation import validator as val_mod


# backend/ on host, /app in container
BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_no_frontend_files_in_daily_observation_package():
    pkg = BACKEND_ROOT / "app" / "services" / "daily_observation"
    for p in pkg.rglob("*"):
        assert p.suffix not in {".jsx", ".tsx", ".css"}


def test_service_source_has_no_writes_or_dispatch():
    src = inspect.getsource(svc_mod)
    for banned in (
        ".commit(",
        ".add(",
        "flush(",
        "sendMessage",
        "GreenAPI",
        "delay(",
        "apply_async",
        "enqueue",
    ):
        assert banned not in src


def test_validator_has_no_db_access():
    src = inspect.getsource(val_mod)
    assert "AsyncSession" not in src
    assert "execute(" not in src
    assert "SELECT" not in src


def test_cli_has_no_mutating_flags():
    src = inspect.getsource(cli)
    assert "--enable" not in src
    assert "--cutover" not in src
    assert "v67_shadow_runtime_enabled=True" not in src


def test_no_new_api_router_for_daily_observation():
    api_dir = BACKEND_ROOT / "app" / "api" / "v1"
    names = [p.name for p in api_dir.glob("*.py")]
    assert "daily_observation.py" not in names
    main_src = (BACKEND_ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "daily_observation" not in main_src


def test_no_new_migration_for_daily_observation():
    versions = BACKEND_ROOT / "migrations" / "versions"
    hits = [p.name for p in versions.glob("*.py") if "daily_observation" in p.name.lower()]
    assert hits == []


def test_migration_guard_module_still_present():
    guard = BACKEND_ROOT / "app" / "services" / "migration_db_guard.py"
    assert guard.is_file()
    txt = guard.read_text(encoding="utf-8")
    assert "whatsapp_sender" in txt or "ENV" in txt or "V67_ALLOW" in txt
