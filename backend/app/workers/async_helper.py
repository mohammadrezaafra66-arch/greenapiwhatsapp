"""Reusable event-loop runner for Celery tasks (B1.1).

asyncio.run() creates and *closes* a fresh event loop on every call. That is
fragile in a long-lived worker: module-level async clients (e.g. the aioredis
client in redis_rate_limiter) get bound to the first loop and then break with
"Event loop is closed" / "attached to a different loop" on the next task.

run_async keeps ONE loop per worker process and reuses it, so those clients stay
valid across tasks. DB safety is unaffected — workers use NullPool, so every
AsyncSession opens fresh connections regardless.
"""
import asyncio

_loop = None


def run_async(coro):
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop.run_until_complete(coro)
