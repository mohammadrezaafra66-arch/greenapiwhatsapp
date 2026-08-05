"""CLI: python -m app.scripts.fleet_score_simulate --account-id ... [--dry-run]

Simulation only. No FleetState mutation. No Green API.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import sys
import uuid

from app.database import AsyncSessionLocal
from app.services.fleet_scoring import FleetScoringService


async def _run(args: argparse.Namespace) -> int:
    account_id = uuid.UUID(args.account_id)
    inject = {
        "suspended": args.inject_suspended,
        "blocked": args.inject_blocked,
        "inactivity": args.inject_inactivity,
        "webhook_failure": args.inject_webhook_failure,
        "breaker": args.inject_breaker,
        "inactivity_days": args.inactivity_days,
    }
    async with AsyncSessionLocal() as db:
        result = await FleetScoringService().simulate(
            db, account_id, inject=inject, persist=bool(args.persist),
        )
        if args.persist and result.get("persisted"):
            await db.commit()
        print(json.dumps(result, indent=2, default=str))
        return 0 if not result.get("error") else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="V67 Phase 4 trust/risk simulation")
    p.add_argument("--account-id", required=True)
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--persist", action="store_true")
    p.add_argument("--inject-suspended", action="store_true")
    p.add_argument("--inject-blocked", action="store_true")
    p.add_argument("--inject-inactivity", action="store_true")
    p.add_argument("--inject-webhook-failure", action="store_true")
    p.add_argument("--inject-breaker", action="store_true")
    p.add_argument("--inactivity-days", type=int, default=14)
    args = p.parse_args(argv)
    if args.persist:
        args.dry_run = False
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
