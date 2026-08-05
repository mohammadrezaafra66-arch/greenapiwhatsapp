"""CLI: python -m app.scripts.fleet_shadow_run --account-id ...

Dry-run by default. No Green API, send, campaign, Journey execution, or flag mutation.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import uuid

from app.database import AsyncSessionLocal
from app.services.shadow_runtime import ShadowRuntimeService
from app.services.shadow_types import ShadowRunSource


async def _run(args: argparse.Namespace) -> int:
    try:
        account_id = uuid.UUID(args.account_id)
    except ValueError:
        print(json.dumps({"error": "invalid_uuid", "account_id": args.account_id}))
        return 2

    inject = {}
    if args.inject_breaker:
        inject["breaker"] = True
    if args.inject_incident:
        inject["incident"] = args.inject_incident
    if args.inject_stale_sensor:
        inject["stale_sensor"] = args.inject_stale_sensor
    if args.inject_runtime_unknown:
        inject["runtime_unknown"] = True
    if args.inject_policy_mismatch:
        inject["policy_mismatch"] = True

    persist = bool(args.persist) and not args.dry_run
    async with AsyncSessionLocal() as db:
        out = await ShadowRuntimeService().run_account(
            db, account_id,
            source=ShadowRunSource.CLI_RUN_ONCE.value,
            persist=persist,
            dry_run=args.dry_run,
            inject=inject,
            require_runtime_flag=False,
        )
        if persist and out.get("persisted"):
            await db.commit()
        if not args.show_evidence and isinstance(out, dict):
            out = {k: v for k, v in out.items() if k not in ("sensor_freshness",)}
        print(json.dumps(out, indent=2, default=str))
        if out.get("error") in ("account_not_found", "fleet_account_missing"):
            return 1
        if out.get("error") == "cutover_true_forbidden":
            return 3
        if out.get("error"):
            return 1
        return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="V67 Phase 7 Shadow run (dry-run default)")
    p.add_argument("--account-id", required=True)
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--no-dry-run", dest="dry_run", action="store_false")
    p.add_argument("--persist", action="store_true", default=False)
    p.add_argument("--show-evidence", action="store_true")
    p.add_argument("--at", default=None, help="Reserved observation timestamp (ISO); unused for slotting")
    p.add_argument("--source", default=ShadowRunSource.CLI_RUN_ONCE.value)
    p.add_argument("--inject-breaker", action="store_true")
    p.add_argument("--inject-incident", default=None)
    p.add_argument("--inject-stale-sensor", default=None)
    p.add_argument("--inject-policy-mismatch", action="store_true")
    p.add_argument("--inject-runtime-unknown", action="store_true")
    return asyncio.run(_run(p.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
