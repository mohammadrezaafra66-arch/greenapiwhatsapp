"""V14 PART G — capability registry helpers.

`record_support` upserts a row into method_support so a plan-restricted (403) method
is permanently marked unsupported, and a 2xx marks it supported. This is how
UNKNOWN-NOT-PROBED methods get classified on first real use, with no risky probing.
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def is_403(exc: Exception) -> bool:
    """True if the exception is (or wraps) an HTTP 403 — a plan restriction."""
    resp = getattr(exc, "response", None)
    if resp is not None and getattr(resp, "status_code", None) == 403:
        return True
    return "403" in str(exc)


async def is_supported(db: AsyncSession, method: str) -> bool | None:
    """Return method_support.supported for `method` (True/False), or None if the
    method has never been recorded. Callers treat None as 'attempt it'."""
    try:
        row = (await db.execute(
            text("SELECT supported FROM method_support WHERE method = :m"), {"m": method}
        )).first()
        return row[0] if row else None
    except Exception:
        return None


async def record_support(
    db: AsyncSession,
    method: str,
    supported: bool | None,
    status_code: int | None = None,
    note: str | None = None,
) -> None:
    """Upsert a method_support row. Never raises on a logging failure."""
    try:
        await db.execute(
            text(
                """
                INSERT INTO method_support (method, supported, last_status_code, last_checked, note)
                VALUES (:m, :s, :c, now(), :n)
                ON CONFLICT (method) DO UPDATE SET
                    supported = EXCLUDED.supported,
                    last_status_code = EXCLUDED.last_status_code,
                    last_checked = now(),
                    note = COALESCE(EXCLUDED.note, method_support.note)
                """
            ),
            {"m": method, "s": supported, "c": status_code, "n": note},
        )
        await db.commit()
    except Exception:
        # capability logging must never break a real request
        await db.rollback()
