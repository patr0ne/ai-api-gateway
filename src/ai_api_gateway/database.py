"""Asynchronous PostgreSQL engine and request-scoped session wiring."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Request
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def make_async_database_url(dsn: str) -> URL:
    """Return a PostgreSQL URL that always uses the asyncpg driver."""

    url = make_url(dsn)
    if url.drivername == "postgresql":
        return url.set(drivername="postgresql+asyncpg")
    if url.drivername != "postgresql+asyncpg":
        raise ValueError("database DSN must use PostgreSQL with asyncpg")
    return url


class Database:
    """Own the application engine and its asynchronous session factory."""

    def __init__(self, dsn: str) -> None:
        self.engine: AsyncEngine = create_async_engine(
            make_async_database_url(dsn),
            pool_pre_ping=True,
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Provide a session whose lifetime is bounded to one request."""

        async with self.session_factory() as session:
            yield session

    async def dispose(self) -> None:
        """Close all pooled database connections during application shutdown."""

        await self.engine.dispose()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields the current application's DB session."""

    database: Database = request.app.state.database
    async with database.session() as session:
        yield session
