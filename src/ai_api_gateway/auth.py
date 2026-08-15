"""API-key fingerprinting and PostgreSQL-backed authentication."""

import hashlib
import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_api_gateway.database import get_session
from ai_api_gateway.models import ApiClient


def fingerprint_api_key(api_key: str, pepper: SecretStr) -> str:
    """Derive the deterministic, indexed fingerprint stored in PostgreSQL."""

    return hmac.new(
        pepper.get_secret_value().encode("utf-8"),
        api_key.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
    )


async def authenticate_api_key(
    api_key: str | None,
    pepper: SecretStr,
    session: AsyncSession,
) -> ApiClient:
    """Return an active client or a deliberately non-enumerating error."""

    if not api_key:
        raise _unauthorized()

    fingerprint = fingerprint_api_key(api_key, pepper)
    statement = select(ApiClient).where(
        ApiClient.key_fingerprint == fingerprint,
        ApiClient.is_active.is_(True),
    )
    try:
        result = await session.execute(statement)
        client = result.scalar_one_or_none()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from exc

    if client is None:
        raise _unauthorized()
    return client


async def require_api_client(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> ApiClient:
    """FastAPI dependency used by endpoints that require a valid client."""

    return await authenticate_api_key(
        api_key,
        request.app.state.settings.api_key_fingerprint_pepper,
        session,
    )
