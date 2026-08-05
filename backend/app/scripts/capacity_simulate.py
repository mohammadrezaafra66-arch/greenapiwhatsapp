"""CLI: python -m app.scripts.capacity_simulate [--account-id] — dry-run only."""
from __future__ import annotations
import argparse
import asyncio
import json
import uuid
import sys

from app.database import AsyncSessionLocal
from app.services.fleet_planning import FleetPlanningService


async def _run(args: argparse.Namespace) -> int:
    aid = uuid.UUID(args.account_id) if args.account_id else None
    async with AsyncSessionLocal() as db:
        out = await FleetPlanningService().capacity_preview(db, account_id=aid)
        out["dry_run"] = True
        print(json.dumps(out, indent=2, default=str))
        return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="V67 Phase 5 capacity simulation (dry-run)")
    p.add_argument("--account-id", default=None)
    p.add_argument("--dry-run", action="store_true", default=True)
    return asyncio.run(_run(p.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
