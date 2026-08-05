"""CLI: python -m app.scripts.fleet_journey_simulate --dry-run ...

No live Green API calls. Default dry-run.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import sys
import uuid

from app.database import AsyncSessionLocal
from app.services.journey_orchestrator import JourneyOrchestrator
from app.services.journey_types import JourneyType


async def _run(args: argparse.Namespace) -> int:
    if not args.account_id:
        print("--account-id required", file=sys.stderr)
        return 2
    account_id = uuid.UUID(args.account_id)
    inject = {
        "suspended": args.inject_suspended,
        "blocked": args.inject_blocked,
        "forced_logout": args.inject_forced_logout,
        "breaker": args.inject_breaker,
        "webhook_stale": args.inject_webhook_stale,
        "days": args.days,
        "elapsed_hours": args.elapsed_hours,
    }
    async with AsyncSessionLocal() as db:
        orch = JourneyOrchestrator()
        if args.persist_simulation and not args.dry_run:
            result = await orch.simulate_and_maybe_persist(
                db, account_id,
                journey_type=args.journey_type,
                persist_simulation=True,
                inject=inject,
            )
            await db.commit()
        else:
            result = await orch.preview(
                db, account_id, journey_type=args.journey_type, inject=inject,
            )
            result = {**result, "dry_run": True, "persisted": False}
        print(json.dumps(result, indent=2, default=str))
        return 0 if not result.get("error") else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="V67 Phase 3 journey simulation (shadow)")
    p.add_argument("--account-id", required=True)
    p.add_argument("--journey-type", default=JourneyType.NEW_ACCOUNT.value)
    p.add_argument("--policy", default="CONSERVATIVE")
    p.add_argument("--at", default=None, help="Unused ISO timestamp placeholder")
    p.add_argument("--days", type=int, default=None)
    p.add_argument("--elapsed-hours", type=float, default=0.0)
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--persist-simulation", action="store_true")
    p.add_argument("--inject-suspended", action="store_true")
    p.add_argument("--inject-blocked", action="store_true")
    p.add_argument("--inject-forced-logout", action="store_true")
    p.add_argument("--inject-breaker", action="store_true")
    p.add_argument("--inject-webhook-stale", action="store_true")
    args = p.parse_args(argv)
    if args.persist_simulation:
        args.dry_run = False
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
