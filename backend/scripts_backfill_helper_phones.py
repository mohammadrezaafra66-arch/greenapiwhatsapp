"""V36 PART 3 one-off: normalize every warmup_helper.phone / phone_secondary to the canonical
international form (0…→98…) so already-stored local-format contacts become matchable.
Run inside the backend container:  python scripts_backfill_helper_phones.py
Guardrails: rewrites ONLY the digit strings on warmup_helper (never the send path / webhook /
mesh / polling); idempotent; no rows added or removed."""
import asyncio, json
from app.database import AsyncSessionLocal
from app.services.warmup_helper_service import backfill_helper_phone_formats


async def main():
    async with AsyncSessionLocal() as db:
        result = await backfill_helper_phone_formats(db)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
