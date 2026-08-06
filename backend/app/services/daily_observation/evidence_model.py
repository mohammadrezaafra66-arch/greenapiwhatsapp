"""Versioned Daily Observation Evidence Bundle (Phase C).

Not a parallel validator. Not a business-action surface. Read-only metadata.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


EVIDENCE_BUNDLE_VERSION = "v67.owner.daily-observation.evidence.1"


class EvidenceClass(str, Enum):
    RUNTIME_VERIFIED = "RUNTIME_VERIFIED"
    STATIC_VERIFIED = "STATIC_VERIFIED"
    PARTIALLY_OBSERVED = "PARTIALLY_OBSERVED"
    NOT_OBSERVABLE = "NOT_OBSERVABLE"


class EvidenceItemStatus(str, Enum):
    PRESENT = "PRESENT"
    MISSING = "MISSING"
    STALE = "STALE"
    MALFORMED = "MALFORMED"
    UNKNOWN = "UNKNOWN"
    VIOLATION = "VIOLATION"


@dataclass
class EvidenceItem:
    invariant: str
    evidence_class: str
    status: str
    source: str
    confidence_class: str
    freshness: str = "UNKNOWN"
    account_scope: str = "global"
    time_range: str | None = None
    correlation_ids: list[str] = field(default_factory=list)
    raw_ref_sanitized: str | None = None
    reason_codes: list[str] = field(default_factory=list)
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DailyObservationEvidenceBundle:
    """v67.owner.daily-observation.evidence.1"""

    evidence_version: str = EVIDENCE_BUNDLE_VERSION
    report_date_utc: str = ""
    session_id: str = "session-2"
    generated_at_utc: str = ""
    deployed_git_sha: str | None = None
    shadow_version: str | None = None
    policy_version: int | None = None
    migration_revision: str | None = None
    runtime_items: list[EvidenceItem] = field(default_factory=list)
    static_items: list[EvidenceItem] = field(default_factory=list)
    partial_items: list[EvidenceItem] = field(default_factory=list)
    missing_items: list[EvidenceItem] = field(default_factory=list)
    correlation_sample: list[dict[str, Any]] = field(default_factory=list)
    correlation_status: str = "UNKNOWN"
    can_support_daily_pass: bool = False
    false_pass_guards: list[str] = field(default_factory=list)
    read_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_version": self.evidence_version,
            "report_date_utc": self.report_date_utc,
            "session_id": self.session_id,
            "generated_at_utc": self.generated_at_utc,
            "deployed_git_sha": self.deployed_git_sha,
            "shadow_version": self.shadow_version,
            "policy_version": self.policy_version,
            "migration_revision": self.migration_revision,
            "runtime_items": [i.to_dict() for i in self.runtime_items],
            "static_items": [i.to_dict() for i in self.static_items],
            "partial_items": [i.to_dict() for i in self.partial_items],
            "missing_items": [i.to_dict() for i in self.missing_items],
            "correlation_sample": list(self.correlation_sample),
            "correlation_status": self.correlation_status,
            "can_support_daily_pass": False if not self.can_support_daily_pass else True,
            "false_pass_guards": list(self.false_pass_guards),
            "read_only": True,
        }

    def owner_safe_dict(self) -> dict[str, Any]:
        """Frontend-safe subset — no secrets, phones, raw messages."""
        d = self.to_dict()
        # Hard honesty: bundle alone never claims PASS capability when guards fire.
        if self.false_pass_guards:
            d["can_support_daily_pass"] = False
        return d
