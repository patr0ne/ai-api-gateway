"""Safe fixtures for tests against disposable PostgreSQL and Redis services."""

import os
from collections.abc import AsyncIterator, Awaitable
from typing import cast
from urllib.parse import urlparse

import pytest
from redis.asyncio import Redis
from sqlalchemy import text

from ai_api_gateway.database import Database, make_async_database_url


@pytest.fixture(scope="session")
def test_postgres_dsn() -> str:
    dsn = os.getenv("TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("TEST_POSTGRES_DSN is not configured")

    url = make_async_database_url(dsn)
    database_name = url.database or ""
    if not database_name.endswith("_test"):
        pytest.fail("TEST_POSTGRES_DSN database name must end with '_test'")
    return dsn


@pytest.fixture(scope="session")
def test_redis_url() -> str:
    url = os.getenv("TEST_REDIS_URL")
    if not url:
        pytest.skip("TEST_REDIS_URL is not configured")

    parsed = urlparse(url)
    try:
        database_number = int(parsed.path.lstrip("/") or "0")
    except ValueError:
        pytest.fail("TEST_REDIS_URL must contain a numeric database")
    if database_number <= 0:
        pytest.fail("TEST_REDIS_URL must use a positive Redis database number")
    return url


@pytest.fixture
async def database(test_postgres_dsn: str) -> AsyncIterator[Database]:
    database = Database(test_postgres_dsn)
    schema_ready = False
    try:
        async with database.engine.begin() as connection:
            await connection.execute(text("TRUNCATE TABLE api_clients"))
        schema_ready = True
        yield database
    finally:
        try:
            if schema_ready:
                async with database.engine.begin() as connection:
                    await connection.execute(text("TRUNCATE TABLE api_clients"))
        finally:
            await database.dispose()


@pytest.fixture
async def redis_client(test_redis_url: str) -> AsyncIterator[Redis]:
    redis = Redis.from_url(test_redis_url, decode_responses=True)
    try:
        await cast(Awaitable[bool], redis.ping())
        await redis.flushdb()
        yield redis
    finally:
        try:
            await redis.flushdb()
        finally:
            await redis.aclose()
