"""CLI: python -m app.scripts.campaign_plan_simulate — dry-run only."""
from __future__ import annotations
import argparse
import asyncio
import json
import sys

from app.database import AsyncSessionLocal
from app.services.fleet_planning import FleetPlanningService


async def _run(args: argparse.Namespace) -> int:
    async with AsyncSessionLocal() as db:
        out = await FleetPlanningService().campaign_plan_simulate(
            db,
            campaign={
                "target_messages": args.target_messages,
                "batch_size": args.batch_size,
                "spacing_minutes": args.spacing_minutes,
            },
            persist=False,
        )
        print(json.dumps(out, indent=2, default=str))
        return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="V67 Phase 5 campaign plan simulation (dry-run)")
    p.add_argument("--target-messages", type=int, default=100)
    p.add_argument("--batch-size", type=int, default=10)
    p.add_argument("--spacing-minutes", type=int, default=20)
    p.add_argument("--dry-run", action="store_true", default=True)
    return asyncio.run(_run(p.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
