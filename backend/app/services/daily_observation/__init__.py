"""Owner Change — Read-Only Daily Observation Report (Phase A/C engine)."""
from app.services.daily_observation.contract import DailyObservationReport
from app.services.daily_observation.session_meta import REPORT_VERSION
from app.services.daily_observation.validator import DailyObservationValidator
from app.services.daily_observation.evidence_model import EVIDENCE_BUNDLE_VERSION

# Heavy imports (DB/settings) stay lazy so pure validator/contract tests collect cleanly.
STATIC_PROOF_VERSION = "v67.owner.daily-observation.static-proof.1"

__all__ = [
    "REPORT_VERSION",
    "EVIDENCE_BUNDLE_VERSION",
    "STATIC_PROOF_VERSION",
    "DailyObservationReport",
    "DailyObservationReportService",
    "DailyObservationValidator",
]


def __getattr__(name: str):
    if name == "DailyObservationReportService":
        from app.services.daily_observation.service import DailyObservationReportService

        return DailyObservationReportService
    raise AttributeError(name)
