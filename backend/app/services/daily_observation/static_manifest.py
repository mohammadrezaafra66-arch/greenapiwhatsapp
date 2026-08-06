"""Versioned Observation Static Proof Manifest (Phase C).

Immutable metadata about the release under test. Does not decide daily PASS alone.
"""
from __future__ import annotations
import os
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.daily_observation.session_meta import REPORT_VERSION
from app.services.shadow_types import SHADOW_VERSION

STATIC_PROOF_VERSION = "v67.owner.daily-observation.static-proof.1"

# Test / isolation references (names only — no secrets).
STATIC_PROOF_REFS = (
    "tests/test_v67_phase7_isolation.py",
    "tests/test_v67_daily_observation_isolation.py",
    "tests/test_v67_daily_observation_readonly_proof.py",
    "send_gate_untouched_by_shadow_path",
    "shadow_never_calls_green_api",
)


@dataclass
class ObservationStaticProofManifest:
    static_proof_version: str = STATIC_PROOF_VERSION
    deployed_git_sha: str | None = None
    source_branch: str | None = None
    shadow_version: str | None = SHADOW_VERSION
    daily_observation_contract_version: str = REPORT_VERSION
    evidence_version: str = "v67.owner.daily-observation.evidence.1"
    migration_revision: str | None = None
    send_gate_integrity_ref: str = "send_gate_untouched_by_shadow_path"
    forbidden_call_test_ref: str = "shadow_never_calls_green_api"
    no_mutation_test_ref: str = "tests/test_v67_daily_observation_readonly_proof.py"
    phase7_isolation_test_ref: str = "tests/test_v67_phase7_isolation.py"
    backend_test_result_ref: str | None = "targeted_v67_daily_observation"
    frontend_build_ref: str | None = "frontend_production_bundle"
    proof_refs: list[str] = field(default_factory=lambda: list(STATIC_PROOF_REFS))
    generated_at_utc: str = ""
    manifest_status: str = "UNKNOWN"  # MATCH | MISMATCH | MISSING | UNKNOWN
    sha_match: bool | None = None
    reason_codes: list[str] = field(default_factory=list)
    read_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["read_only"] = True
        return d


def resolve_deployed_git_sha() -> str | None:
    """Prefer explicit deploy env; then .deployed_git_sha; then local git HEAD."""
    for key in ("V67_DEPLOYED_GIT_SHA", "DEPLOYED_GIT_SHA", "GIT_COMMIT", "GIT_SHA"):
        v = (os.environ.get(key) or "").strip()
        if v:
            return v[:64]
    # backend root in compose is /app; file written at deploy time (no .git in image).
    here = Path(__file__).resolve()
    for candidate in (
        here.parents[3] / ".deployed_git_sha",  # /app/.deployed_git_sha
        here.parents[4] / ".deployed_git_sha",  # repo root when running from host tree
        Path("/app/.deployed_git_sha"),
    ):
        try:
            if candidate.is_file():
                v = candidate.read_text(encoding="utf-8").strip().splitlines()[0].strip()
                if v and not v.startswith("#"):
                    return v[:64]
        except Exception:
            pass
    for root in (here.parents[4], here.parents[3], Path.cwd()):
        try:
            out = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=str(root),
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
            sha = out.decode().strip()[:64]
            if sha:
                return sha
        except Exception:
            continue
    return None


def resolve_source_branch() -> str | None:
    v = (os.environ.get("V67_SOURCE_BRANCH") or os.environ.get("GIT_BRANCH") or "").strip()
    if v:
        return v[:128]
    try:
        root = Path(__file__).resolve().parents[4]
        out = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(root),
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        return out.decode().strip()[:128] or None
    except Exception:
        return None


def build_static_manifest(
    *,
    migration_revision: str | None = None,
    expected_sha: str | None = None,
    now_utc: datetime | None = None,
) -> ObservationStaticProofManifest:
    now = now_utc or datetime.utcnow()
    deployed = resolve_deployed_git_sha()
    expected = (expected_sha or deployed)
    m = ObservationStaticProofManifest(
        deployed_git_sha=deployed,
        source_branch=resolve_source_branch(),
        shadow_version=SHADOW_VERSION,
        migration_revision=migration_revision,
        generated_at_utc=now.isoformat() + "Z",
    )
    if not deployed:
        m.manifest_status = "MISSING"
        m.sha_match = None
        m.reason_codes.append("DEPLOYED_SHA_UNAVAILABLE")
        return m
    if expected and deployed != expected:
        # When expected equals deployed (default), this path is unused.
        m.manifest_status = "MISMATCH"
        m.sha_match = False
        m.reason_codes.append("DEPLOYED_SHA_MISMATCH")
        return m
    m.manifest_status = "MATCH"
    m.sha_match = True
    m.reason_codes.append("DEPLOYED_SHA_RESOLVED")
    return m


def evaluate_sha_against_manifest(
    manifest: ObservationStaticProofManifest,
    *,
    runtime_sha: str | None,
) -> ObservationStaticProofManifest:
    """Fail-closed compare of an independently supplied runtime/deploy SHA."""
    if not manifest.deployed_git_sha:
        manifest.manifest_status = "MISSING"
        manifest.sha_match = None
        if "DEPLOYED_SHA_UNAVAILABLE" not in manifest.reason_codes:
            manifest.reason_codes.append("DEPLOYED_SHA_UNAVAILABLE")
        return manifest
    if not runtime_sha:
        # Cannot confirm match → reduce evidence, do not invent PASS.
        if manifest.manifest_status == "MATCH":
            manifest.manifest_status = "UNKNOWN"
            manifest.sha_match = None
            manifest.reason_codes.append("RUNTIME_SHA_UNAVAILABLE_FOR_COMPARE")
        return manifest
    if runtime_sha != manifest.deployed_git_sha:
        manifest.manifest_status = "MISMATCH"
        manifest.sha_match = False
        manifest.reason_codes.append("DEPLOYED_SHA_MISMATCH")
        return manifest
    manifest.manifest_status = "MATCH"
    manifest.sha_match = True
    return manifest
