"""V40 FIX — one-time repair: free stories an AI outage cached as empty BEFORE the vision guard.

Context. `story_analyzer` sets analysis_type="image" before calling vision and swallows failures,
so while every vision key was rate-limited a bulk run cached each image story as
(analysis_type='image', detected_product_name=NULL) — indistinguishable from a genuine "the model
saw no product". Combined with the analyze-once rule and `is_stale`'s analysis_type='text'
condition, those stories were locked out of re-analysis permanently.

`analyze_story_once` now refuses to cache a failed-vision result at all, so this can no longer
happen. This script exists solely to undo the rows written before that guard landed.

The CUTOFF is mandatory and is the whole safety mechanism: only rows analyzed at/before it are
purged. Post-guard rows are real results and must never be swept up. Pass the moment the guard went
live (or the end of the known outage window).

Usage (inside the backend container):
    python -m scripts.v40_purge_failed_vision --before "2026-07-22 20:00:00"           # dry-run
    python -m scripts.v40_purge_failed_vision --before "2026-07-22 20:00:00" --apply
"""
import asyncio
import json
import sys
from datetime import datetime

from app.database import AsyncSessionLocal
from app.services.story_reanalysis import purge_failed_vision_analyses


def _cutoff_from_argv(argv) -> datetime | None:
    if "--before" not in argv:
        return None
    raw = argv[argv.index("--before") + 1]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


async def main(apply: bool, cutoff: datetime) -> int:
    async with AsyncSessionLocal() as db:
        stats = await purge_failed_vision_analyses(db, cutoff=cutoff, dry_run=not apply)
        if apply:
            await db.commit()
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    if not apply:
        print("\nDRY RUN — nothing was changed. Re-run with --apply.")
    else:
        print(f"\nPurged {stats['deleted']}; those stories are eligible for re-analysis again.")
    return 0


if __name__ == "__main__":
    cut = _cutoff_from_argv(sys.argv)
    if cut is None:
        print('ERROR: --before "YYYY-MM-DD HH:MM:SS" is required (it is the safety bound).')
        sys.exit(2)
    sys.exit(asyncio.run(main("--apply" in sys.argv, cut)))
