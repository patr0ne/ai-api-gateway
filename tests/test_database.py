"""Tests for asynchronous database configuration."""

import pytest

from ai_api_gateway.database import make_async_database_url


def test_plain_postgresql_dsn_is_normalized_to_asyncpg() -> None:
    url = make_async_database_url("postgresql://user:secret@db/gateway")

    assert url.drivername == "postgresql+asyncpg"
    assert url.database == "gateway"


def test_explicit_asyncpg_dsn_is_preserved() -> None:
    url = make_async_database_url("postgresql+asyncpg://user@db/gateway")

    assert url.drivername == "postgresql+asyncpg"


def test_non_postgresql_dsn_is_rejected() -> None:
    with pytest.raises(ValueError, match="PostgreSQL with asyncpg"):
        make_async_database_url("sqlite+aiosqlite:///gateway.db")
