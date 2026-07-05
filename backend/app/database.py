from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from app.config import settings

# Two pooling modes (A1 — scaling):
#  • Celery workers (worker_mode=True): NullPool. Each task runs via asyncio.run()
#    (a fresh event loop per task); pooled asyncpg conns are bound to the loop that
#    created them, so a reused conn on a new loop raises "another operation in
#    progress". NullPool sidesteps this by never reusing connections.
#  • API (worker_mode=False): a real AsyncAdaptedQueuePool. uvicorn serves on a
#    single persistent loop, so pooled connections stay valid — needed to handle
#    many concurrent requests (80 accounts) without exhausting connections.
if settings.worker_mode:
    engine = create_async_engine(settings.database_url, echo=settings.debug, poolclass=NullPool)
else:
    engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_size=20,          # base connections
        max_overflow=40,       # burst capacity → 60 total
        pool_timeout=30,
        pool_recycle=1800,     # recycle every 30 min (avoid stale conns)
        pool_pre_ping=True,    # validate connection before use
    )
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
