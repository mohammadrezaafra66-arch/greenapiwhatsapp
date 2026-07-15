"""One-shot: fill accounts.phone from getWaSettings for every instance whose phone is null.
Run inside the backend container:  python scripts_run_backfill_phones.py
Read-only guardrails: touches only accounts.phone (never the send path / webhook / polling)."""
import asyncio, json
from app.database import AsyncSessionLocal
from app.services.warmup_mesh_service import backfill_account_phones


async def main():
    async with AsyncSessionLocal() as db:
        results = await backfill_account_phones(db)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
