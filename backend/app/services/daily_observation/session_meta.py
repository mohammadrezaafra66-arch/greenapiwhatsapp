"""Logical Session 2 boundary (not a DB entity). Source: docs/v67/107."""
from __future__ import annotations
from datetime import datetime

# Official Session 2 start — first CELERY_PERIODIC snapshot (ops doc 107).
SESSION_2_STARTED_AT_UTC = datetime(2026, 8, 5, 19, 13, 46, 331651)
SESSION_2_ID = "session-2"
SESSION_2_LABEL = "نشست دوم (Session 2)"
SESSION_2_RUN_ID = "9197e53f-4a25-404f-92b8-ad8a8d5e6acf"
EXPECTED_TOTAL_DAYS = 14

# Must match celery beat entry fleet-shadow-tick schedule in celery_app.py.
# Not a Settings field; versioned mirror of the live Beat schedule.
PERIODIC_TICK_INTERVAL_SECONDS = 300

# Tick gap tolerance is not owner-ratified → cannot invent a soft window.
TICK_TOLERANCE_STATUS = "UNRATIFIED"
TICK_TOLERANCE_SECONDS = None

PERIODIC_SOURCE = "CELERY_PERIODIC"
MANUAL_SOURCES = frozenset({"API_RUN_ONCE", "CLI_RUN_ONCE", "TEST"})

REPORT_VERSION = "v67.owner.daily-observation.1"
SOURCE_ENVIRONMENT = "ENV-A"
