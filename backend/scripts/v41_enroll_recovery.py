"""V41 PART 4 — live runner: check the two hard-stop conditions, then enroll (or halt+report).

Usage (inside the backend container, which has the production DB config):
    python -m scripts.v41_enroll_recovery            # dry-run: report breaker + peer finding only
    python -m scripts.v41_enroll_recovery --apply    # enroll ONLY if breaker not tripped AND a safe peer exists

The --apply path still refuses to proceed if the breaker is tripped or no account qualifies as a
safe peer under the existing rules — those two decisions require an explicit human choice, so this
never relaxes the breaker or picks an ineligible peer on its own.
"""
import asyncio
import json
import sys

from app.database import AsyncSessionLocal
from app.services.warmup_killswitch import is_breaker_tripped
from app.services.warmup_recovery_enroll import (
    RECOVERY_TARGET_INSTANCE, select_safe_peer, enroll_recovery_mode,
)
from app.services.warmup_exclusion import enrollment_states_by_instance


async def _report(db, target: str) -> dict:
    breaker = await is_breaker_tripped(db)
    peer = await select_safe_peer(db, target)
    enr_map = await enrollment_states_by_instance(db)
    others_enabled = [iid for iid, (_s, en) in enr_map.items() if iid != target and en]
    return {"target": target, "breaker_tripped": breaker,
            "peer_qualifies": peer["qualifies"], "peer": peer["peer"],
            "candidates": peer["candidates"], "other_enabled_instances": others_enabled}


async def main(apply: bool) -> int:
    target = RECOVERY_TARGET_INSTANCE
    async with AsyncSessionLocal() as db:
        report = await _report(db, target)
        print("=== V41 PART 4 pre-flight ===")
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))

        if report["breaker_tripped"]:
            print("\nHALT: chain-ban breaker is TRIPPED. Not enrolling and NOT resetting it. "
                  "Awaiting explicit user confirmation.")
            return 2
        if not report["peer_qualifies"]:
            print("\nHALT: no currently-connected account passes the existing peer-eligibility bar. "
                  "Not picking an ineligible peer. Awaiting explicit user confirmation on whether to "
                  "relax the peer bar for this monitored recovery cycle.")
            return 3

        if not apply:
            print("\nDRY-RUN: both conditions OK. Re-run with --apply to enroll.")
            return 0

        result = await enroll_recovery_mode(db, target)
        print("\n=== enrolled ===")
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        if result.get("halted"):
            return 2
        if not result.get("others_unchanged") or result.get("other_enabled_instances"):
            print("\nWARNING: another account's enrollment changed — investigate before continuing.")
            return 4
        return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv[1:]
    raise SystemExit(asyncio.run(main(apply)))
