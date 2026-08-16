"""Complete ASGI flow with real storage services and a mocked provider."""

from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from redis.asyncio import Redis

from ai_api_gateway.app import create_app
from ai_api_gateway.auth import fingerprint_api_key
from ai_api_gateway.config import Settings
from ai_api_gateway.database import Database
from ai_api_gateway.models import ApiClient
from ai_api_gateway.upstream import UpstreamClient

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

TEST_PEPPER = SecretStr("integration-test-pepper-value-32")


async def test_complete_gateway_flow_enforces_auth_and_real_redis_limit(
    database: Database,
    redis_client: Redis,
    test_postgres_dsn: str,
    test_redis_url: str,
) -> None:
    assert await redis_client.dbsize() == 0
    first_key = "first-client-api-key"
    second_key = "second-client-api-key"
    revoked_key = "revoked-client-api-key"

    async with database.session() as session:
        session.add_all(
            [
                ApiClient(
                    name="first gateway client",
                    key_fingerprint=fingerprint_api_key(first_key, TEST_PEPPER),
                ),
                ApiClient(
                    name="second gateway client",
                    key_fingerprint=fingerprint_api_key(second_key, TEST_PEPPER),
                ),
                ApiClient(
                    name="revoked gateway client",
                    key_fingerprint=fingerprint_api_key(revoked_key, TEST_PEPPER),
                    is_active=False,
                ),
            ]
        )
        await session.commit()

    settings = Settings(
        database_dsn=test_postgres_dsn,
        redis_url=test_redis_url,
        api_key_fingerprint_pepper=TEST_PEPPER,
        upstream_base_url="https://provider.invalid/v1/",
        upstream_api_key="integration-provider-key",
        _env_file=None,
    )
    application = create_app(settings)
    upstream = AsyncMock(spec=UpstreamClient)
    upstream.generate.return_value = httpx.Response(
        200,
        json={"result": "generated"},
        headers={"Content-Type": "application/json"},
    )

    with TestClient(application) as client:
        application.state.upstream_client = upstream
        first_responses = [
            client.post(
                "/v1/generate",
                headers={"X-API-Key": first_key},
                json={"prompt": f"request {number}"},
            )
            for number in range(1, 7)
        ]
        second_response = client.post(
            "/v1/generate",
            headers={"X-API-Key": second_key},
            json={"prompt": "independent request"},
        )
        revoked_response = client.post(
            "/v1/generate",
            headers={"X-API-Key": revoked_key},
            json={"prompt": "must be rejected"},
        )

    assert [response.status_code for response in first_responses] == [
        200,
        200,
        200,
        200,
        200,
        429,
    ]
    assert [
        response.headers["X-RateLimit-Remaining"] for response in first_responses
    ] == ["4", "3", "2", "1", "0", "0"]
    assert first_responses[-1].headers["Retry-After"].isdigit()
    assert second_response.status_code == 200
    assert second_response.headers["X-RateLimit-Remaining"] == "4"
    assert revoked_response.status_code == 401
    assert upstream.generate.await_count == 6
