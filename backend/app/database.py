from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from app.config import settings

# NullPool: never reuse a connection across checkouts. Required because Celery
# runs each task via asyncio.run() (a fresh event loop per task) and asyncpg
# connections are bound to the loop that created them — a pooled connection
# reused on a different loop raises "another operation is in progress".
engine = create_async_engine(settings.database_url, echo=settings.debug, poolclass=NullPool)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
