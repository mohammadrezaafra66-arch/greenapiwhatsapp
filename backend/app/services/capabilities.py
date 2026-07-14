"""V14 PART G — capability registry helpers.

`record_support` upserts a row into method_support so a plan-restricted (403) method
is permanently marked unsupported, and a 2xx marks it supported. This is how
UNKNOWN-NOT-PROBED methods get classified on first real use, with no risky probing.
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


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
