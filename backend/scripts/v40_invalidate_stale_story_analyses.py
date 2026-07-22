"""V40 FIX — live runner: repair stories the media-type bug mis-stored, then free them for re-analysis.

Before the `normalize_status` fix, every status was classified "incoming" (Green API's direction
value), so no story image was downloaded and every image story was analyzed as text. Repairing that
takes three ordered steps, all of which this runs:

  1. REPAIR   — reclassify status_type "incoming" → image/text on the already-stored rows.
                `persist_incoming_statuses` skips rows that already exist, so a re-fetch can never
                fix them; without this step the next two accomplish nothing.
  2. MEDIA    — download the still-missing images to local storage. Green API media URLs expire
                ~24h after the story was posted, so some are already dead; failures are counted,
                never fatal.
  3. RECLASSIFY — correct status_type from the downloaded bytes, so video/audio statuses never
                reach the image-only vision path and waste an AI call.
  4. INVALIDATE — delete the cached analyses that never saw an image, so those stories are eligible
                for a real vision re-analysis. Analyses that DETECTED a product are never touched.

Usage (inside the backend container, which has the production DB config):
    python -m scripts.v40_invalidate_stale_story_analyses              # dry-run: report only
    python -m scripts.v40_invalidate_stale_story_analyses --apply      # perform all three steps
    python -m scripts.v40_invalidate_stale_story_analyses --only-empty # narrow step 3 to caption-less
    python -m scripts.v40_invalidate_stale_story_analyses --skip-media # steps 1 + 3 only
"""
import asyncio
import json
import sys

from app.database import AsyncSessionLocal
from app.services.story_reanalysis import (
    repair_legacy_status_types, backfill_missing_media, reclassify_from_downloaded_media,
    invalidate_stale_analyses,
)


async def main(apply: bool, only_empty: bool, skip_media: bool) -> int:
    dry = not apply
    async with AsyncSessionLocal() as db:
        report = {"repair": await repair_legacy_status_types(db, dry_run=dry)}
        # Flush the reclassification before the media pass so both see one consistent state.
        if apply:
            await db.flush()
        report["media"] = ({"skipped": True} if skip_media
                           else await backfill_missing_media(db, dry_run=dry))
        if apply:
            await db.flush()
        # Videos/audio look identical to images on a stored row (no typeMessage survives), so correct
        # the type from the bytes we just downloaded — a video sent to vision burns an AI call.
        report["reclassify"] = await reclassify_from_downloaded_media(db, dry_run=dry)
        if apply:
            await db.flush()
        report["invalidate"] = await invalidate_stale_analyses(
            db, only_empty=only_empty, dry_run=dry)
        if apply:
            await db.commit()

    print(json.dumps(report, indent=2, ensure_ascii=False))
    if dry:
        print("\nDRY RUN — nothing was changed. Re-run with --apply.")
    else:
        inv = report["invalidate"]
        print(f"\nRepaired {report['repair']['repaired']} status rows; "
              f"downloaded {report['media'].get('downloaded', 0)} images; "
              f"invalidated {inv['deleted']} analyses.")
        print(f"{inv['deleted']} stories are now eligible for re-analysis.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(
        "--apply" in sys.argv, "--only-empty" in sys.argv, "--skip-media" in sys.argv)))
