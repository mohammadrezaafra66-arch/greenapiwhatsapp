"""CLI: python -m app.scripts.eligibility_simulate --account-id ...

Dry-run decision only. No runtime mutation.
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
    account_id = uuid.UUID(args.account_id)
    inject = {
        "breaker": args.inject_breaker,
        "suspended": args.inject_suspended,
        "blocked": args.inject_blocked,
        "fleet_state": args.fleet_state,
        "trust_score": args.trust_score,
        "risk_level": args.risk_level,
        "readiness_label": args.readiness,
        "daily_capacity": args.daily_capacity,
        "recommended_usage": args.recommended_usage,
    }
    # drop Nones
    inject = {k: v for k, v in inject.items() if v is not None and v is not False}
    if args.inject_breaker:
        inject["breaker"] = True
    if args.inject_suspended:
        inject["suspended"] = True
    if args.inject_blocked:
        inject["blocked"] = True

    async with AsyncSessionLocal() as db:
        out = await EligibilityService().preview(db, account_id, inject=inject, persist=False)
        print(json.dumps(out, indent=2, default=str))
        return 0 if not out.get("error") else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="V67 Phase 6 eligibility simulation (dry-run)")
    p.add_argument("--account-id", required=True)
    p.add_argument("--dry-run", action="store_true", default=True)
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
