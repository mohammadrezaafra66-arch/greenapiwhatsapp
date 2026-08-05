"""CLI: python -m app.scripts.fleet_seed --dry-run [--account-id UUID] [--batch-size N] [--apply]

Never calls Green API. Default is dry-run.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import uuid
import sys

from app.database import AsyncSessionLocal
from app.services import fleet_seed


async def _run(args: argparse.Namespace) -> int:
    account_id = uuid.UUID(args.account_id) if args.account_id else None
    async with AsyncSessionLocal() as db:
        plans = await fleet_seed.build_seed_plan(
            db, account_id=account_id, batch_size=args.batch_size,
        )
        print(json.dumps({
            "dry_run": not args.apply,
            "count": len(plans),
            "plans": fleet_seed.plans_as_dicts(plans),
        }, indent=2, default=str))
        if not args.apply:
            print("No changes applied (dry-run). Pass --apply to write.", file=sys.stderr)
            return 0
        await fleet_seed.ensure_default_conservative_policy(db)
        result = await fleet_seed.apply_seed_plan(db, plans)
        await db.commit()
        print(json.dumps({"applied": True, **result}, indent=2))
        return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="V67 Phase 2 fleet seed/backfill")
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="Preview only (default)")
    p.add_argument("--apply", action="store_true",
                   help="Apply planned creates/updates (explicit)")
    p.add_argument("--account-id", default=None, help="Limit to one account UUID")
    p.add_argument("--batch-size", type=int, default=200)
    args = p.parse_args(argv)
    if args.apply:
        args.dry_run = False
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
