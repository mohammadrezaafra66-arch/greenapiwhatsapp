"""V67 Phase 7 — Shadow domain contracts."""
from __future__ import annotations
import enum
from dataclasses import dataclass, asdict, field
from typing import Any


SHADOW_VERSION = "v67.7.shadow.1"


class ShadowMismatchClass(str, enum.Enum):
    MATCH = "MATCH"
    SAFE_MISMATCH = "SAFE_MISMATCH"
    DANGEROUS_MISMATCH = "DANGEROUS_MISMATCH"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    LEGACY_MORE_PERMISSIVE = "LEGACY_MORE_PERMISSIVE"
    V67_MORE_PERMISSIVE = "V67_MORE_PERMISSIVE"
    POLICY_VERSION_MISMATCH = "POLICY_VERSION_MISMATCH"
    SENSOR_STALE = "SENSOR_STALE"
    RUNTIME_UNKNOWN = "RUNTIME_UNKNOWN"


class ShadowSeverity(str, enum.Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ShadowThresholdStatus(str, enum.Enum):
    UNRATIFIED = "UNRATIFIED"


class ShadowRunSource(str, enum.Enum):
    API_RUN_ONCE = "API_RUN_ONCE"
    CLI_RUN_ONCE = "CLI_RUN_ONCE"
    CELERY_PERIODIC = "CELERY_PERIODIC"
    TEST = "TEST"


@dataclass(frozen=True)
class ShadowComparisonResult:
    mismatch_class: str
    severity: str
    reason_codes: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    stale_sensors: tuple[str, ...]
    legacy_more_permissive: bool
    v67_more_permissive: bool
    policy_mismatch: bool
    details: dict[str, Any] = field(default_factory=dict)
    shadow_version: str = SHADOW_VERSION
    dangerous_threshold_status: str = ShadowThresholdStatus.UNRATIFIED.value
    simulation_only: bool = True
    mutates_runtime: bool = False
    executes: bool = False

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["reason_codes"] = list(self.reason_codes)
        d["missing_evidence"] = list(self.missing_evidence)
        d["stale_sensors"] = list(self.stale_sensors)
        return d


def idempotency_key(
    account_id: str,
    shadow_version: str,
    policy_version: int | None,
    scheduled_slot: str | None,
    source: str,
) -> str:
    slot = scheduled_slot or "adhoc"
    pv = str(policy_version if policy_version is not None else "none")
    return f"{account_id}:{shadow_version}:{pv}:{slot}:{source}"
