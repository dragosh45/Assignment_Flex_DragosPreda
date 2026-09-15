from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config import settings


class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None

    async def initialize(self):
        if self.session_factory is not None:
            return
        # Compose supplies DATABASE_URL. Async engines choose their own async pool.
        url = make_url(settings.database_url).set(drivername="postgresql+asyncpg")
        self.engine = create_async_engine(url, pool_pre_ping=True, pool_recycle=3600)
        self.session_factory = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def close(self):
        if self.engine is not None:
            await self.engine.dispose()
        self.engine = None
        self.session_factory = None

    def get_session(self) -> AsyncSession:
        # Return the context manager directly, rather than a coroutine.
        if self.session_factory is None:
            raise RuntimeError("Database pool not initialized")
        return self.session_factory()


db_pool = DatabasePool()


async def get_db_session():
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        yield session
