"""PostgreSQL migration and API-key authentication integration tests."""

import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import text

from ai_api_gateway.auth import authenticate_api_key, fingerprint_api_key
from ai_api_gateway.database import Database
from ai_api_gateway.models import ApiClient

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

TEST_PEPPER = SecretStr("integration-test-pepper-value-32")


async def test_migrated_schema_authenticates_only_active_clients(
    database: Database,
) -> None:
    active_key = "active-client-key"
    revoked_key = "revoked-client-key"

    async with database.session() as session:
        migration = await session.execute(
            text("SELECT version_num FROM alembic_version")
        )
        assert migration.scalar_one() == "0001"
        session.add_all(
            [
                ApiClient(
                    name="active integration client",
                    key_fingerprint=fingerprint_api_key(active_key, TEST_PEPPER),
                ),
                ApiClient(
                    name="revoked integration client",
                    key_fingerprint=fingerprint_api_key(revoked_key, TEST_PEPPER),
                    is_active=False,
                ),
            ]
        )
        await session.commit()

    async with database.session() as session:
        client = await authenticate_api_key(active_key, TEST_PEPPER, session)
        assert client.name == "active integration client"

    async with database.session() as session:
        with pytest.raises(HTTPException) as exc_info:
            await authenticate_api_key(revoked_key, TEST_PEPPER, session)

    assert exc_info.value.status_code == 401
