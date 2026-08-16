"""Unit tests for API-key fingerprinting and authentication decisions."""

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_api_gateway.auth import authenticate_api_key, fingerprint_api_key
from ai_api_gateway.models import ApiClient


def test_fingerprint_is_stable_hmac_sha256() -> None:
    fingerprint = fingerprint_api_key(
        "client-secret",
        SecretStr("p" * 32),
    )

    assert fingerprint == (
        "d73b2461fd1d1309c1f9d2d0502aa6355068d1feb291cabc49ea140c615fbc4a"
    )
    assert "client-secret" not in fingerprint


@pytest.mark.anyio
async def test_authentication_returns_active_client() -> None:
    expected_client = ApiClient(
        name="test client",
        key_fingerprint="f" * 64,
    )
    result = Mock()
    result.scalar_one_or_none.return_value = expected_client
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = result

    client = await authenticate_api_key(
        "client-secret",
        SecretStr("p" * 32),
        session,
    )

    assert client is expected_client
    session.execute.assert_awaited_once()
    statement = session.execute.await_args.args[0]
    parameters = statement.compile().params.values()
    assert fingerprint_api_key("client-secret", SecretStr("p" * 32)) in parameters
    assert "client-secret" not in parameters
    assert "api_clients.is_active IS true" in str(statement)


@pytest.mark.anyio
@pytest.mark.parametrize("api_key", [None, "unknown-or-revoked-key"])
async def test_missing_invalid_or_revoked_key_has_same_401_detail(
    api_key: str | None,
) -> None:
    result = Mock()
    result.scalar_one_or_none.return_value = None
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = result

    with pytest.raises(HTTPException) as exc_info:
        await authenticate_api_key(
            api_key,
            SecretStr("p" * 32),
            session,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid API key"
    if api_key is None:
        session.execute.assert_not_awaited()


@pytest.mark.anyio
async def test_database_failure_fails_authentication_closed() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = SQLAlchemyError("database unavailable")

    with pytest.raises(HTTPException) as exc_info:
        await authenticate_api_key(
            "client-secret",
            SecretStr("p" * 32),
            session,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Authentication service unavailable"
