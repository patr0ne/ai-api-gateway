"""Restricted asynchronous client and route for the configured AI provider."""

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import JsonValue

from ai_api_gateway.rate_limit import RateLimitGrant, enforce_rate_limit

UPSTREAM_GENERATE_PATH = "generate"


class UpstreamTimeoutError(RuntimeError):
    """Raised when the configured provider exceeds its request timeout."""


class UpstreamTransportError(RuntimeError):
    """Raised when no valid HTTP response can be obtained from the provider."""


class UpstreamClient:
    """Forward allowed payloads to one server-configured endpoint."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http_client = http_client

    async def generate(self, payload: dict[str, JsonValue]) -> httpx.Response:
        try:
            return await self._http_client.post(
                UPSTREAM_GENERATE_PATH,
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError from exc
        except httpx.RequestError as exc:
            raise UpstreamTransportError from exc


router = APIRouter()


@router.post("/v1/generate", tags=["gateway"])
async def generate(
    request: Request,
    payload: dict[str, JsonValue],
    grant: Annotated[RateLimitGrant, Depends(enforce_rate_limit)],
) -> Response:
    """Forward a validated JSON object after authentication and rate limiting."""

    upstream: UpstreamClient = request.app.state.upstream_client
    try:
        upstream_response = await upstream.generate(payload)
    except UpstreamTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Upstream request timed out",
            headers=grant.decision.headers(),
        ) from exc
    except UpstreamTransportError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Upstream service unavailable",
            headers=grant.decision.headers(),
        ) from exc

    headers = grant.decision.headers()
    content_type = upstream_response.headers.get("content-type")
    if content_type is not None:
        headers["Content-Type"] = content_type

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=headers,
    )
