"""CLI: python -m app.scripts.eligibility_simulate --account-id ...

Dry-run decision only by default. No runtime mutation.
Pass --persist only to write a simulation snapshot (never when cutover=true).
"""
from __future__ import annotations
import argparse
import asyncio
import json
import uuid
import sys

from app.database import AsyncSessionLocal
from app.services.eligibility_service import EligibilityService


async def _run(args: argparse.Namespace) -> int:
    try:
        account_id = uuid.UUID(args.account_id)
    except ValueError:
        print(json.dumps({"error": "invalid_uuid", "account_id": args.account_id}))
        return 2

    inject = {
        "fleet_state": args.fleet_state,
        "trust_score": args.trust_score,
        "risk_level": args.risk_level,
        "readiness_label": args.readiness,
        "daily_capacity": args.daily_capacity,
        "recommended_usage": args.recommended_usage,
    }
    inject = {k: v for k, v in inject.items() if v is not None}
    if args.inject_breaker:
        inject["breaker"] = True
    if args.inject_suspended:
        inject["suspended"] = True
    if args.inject_blocked:
        inject["blocked"] = True

    persist = bool(args.persist) and not args.dry_run
    async with AsyncSessionLocal() as db:
        out = await EligibilityService().preview(
            db, account_id, inject=inject, persist=persist,
        )
        if persist and out.get("persisted"):
            await db.commit()
        print(json.dumps(out, indent=2, default=str))
        if out.get("error") == "account_not_found":
            return 1
        if out.get("error"):
            return 1
        return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="V67 Phase 6 eligibility simulation (dry-run default; no live send)",
    )
    p.add_argument("--account-id", required=True)
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Do not persist snapshot (default). Explicit dry-run for forward compatibility.",
    )
    p.add_argument(
        "--persist",
        action="store_true",
        default=False,
        help="Persist eligibility snapshot only (still simulation_only; refuses cutover=true).",
    )
    p.add_argument("--no-dry-run", dest="dry_run", action="store_false",
                   help="Allow --persist to take effect.")
    p.add_argument("--inject-breaker", action="store_true")
    p.add_argument("--inject-suspended", action="store_true")
    p.add_argument("--inject-blocked", action="store_true")
    p.add_argument("--fleet-state", default=None)
    p.add_argument("--trust-score", type=float, default=None)
    p.add_argument("--risk-level", default=None)
    p.add_argument("--readiness", default=None)
    p.add_argument("--daily-capacity", type=int, default=None)
    p.add_argument("--recommended-usage", type=int, default=None)
    return asyncio.run(_run(p.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
