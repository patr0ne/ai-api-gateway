"""Tests for restricted upstream forwarding and gateway error mapping."""

import json
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from ai_api_gateway.app import create_app
from ai_api_gateway.config import Settings
from ai_api_gateway.models import ApiClient
from ai_api_gateway.rate_limit import (
    RateLimitDecision,
    RateLimitGrant,
    enforce_rate_limit,
)
from ai_api_gateway.upstream import (
    UpstreamClient,
    UpstreamTimeoutError,
    UpstreamTransportError,
)


@asynccontextmanager
async def _upstream_with_handler(
    handler: Callable[[httpx.Request], httpx.Response],
) -> AsyncIterator[UpstreamClient]:
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        base_url="https://provider.invalid/v1/",
        headers={"Authorization": "Bearer provider-secret"},
        transport=transport,
    ) as http_client:
        yield UpstreamClient(http_client)


@pytest.mark.anyio
async def test_client_posts_json_only_to_fixed_configured_endpoint() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(201, json={"result": "generated"})

    async with _upstream_with_handler(handler) as upstream:
        response = await upstream.generate({"prompt": "hello"})

    assert response.status_code == 201
    assert captured_request is not None
    assert str(captured_request.url) == "https://provider.invalid/v1/generate"
    assert captured_request.headers["Authorization"] == "Bearer provider-secret"
    assert json.loads(captured_request.content) == {"prompt": "hello"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("transport_error_type", "expected_error"),
    [
        (httpx.ReadTimeout, UpstreamTimeoutError),
        (httpx.ConnectError, UpstreamTransportError),
    ],
)
async def test_client_maps_timeout_and_transport_failures(
    transport_error_type: type[httpx.RequestError],
    expected_error: type[Exception],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise transport_error_type("private provider failure", request=request)

    async with _upstream_with_handler(handler) as upstream:
        with pytest.raises(expected_error):
            await upstream.generate({"prompt": "hello"})


@contextmanager
def _gateway_client(
    settings: Settings,
    upstream_result: httpx.Response | Exception,
) -> Iterator[tuple[TestClient, AsyncMock]]:
    application = create_app(settings)
    grant = RateLimitGrant(
        client=ApiClient(
            id=uuid4(),
            name="test client",
            key_fingerprint="f" * 64,
        ),
        decision=RateLimitDecision(
            allowed=True,
            current=1,
            remaining=4,
            retry_after=60,
        ),
    )

    async def allowed_request() -> RateLimitGrant:
        return grant

    application.dependency_overrides[enforce_rate_limit] = allowed_request
    upstream = AsyncMock(spec=UpstreamClient)
    if isinstance(upstream_result, Exception):
        upstream.generate.side_effect = upstream_result
    else:
        upstream.generate.return_value = upstream_result

    with TestClient(application) as client:
        application.state.upstream_client = upstream
        yield client, upstream


def test_proxy_returns_upstream_status_body_and_safe_headers(
    settings: Settings,
) -> None:
    upstream_response = httpx.Response(
        201,
        json={"result": "generated"},
        headers={
            "Content-Type": "application/json",
            "Set-Cookie": "provider-cookie=must-not-leak",
        },
    )
    with _gateway_client(settings, upstream_response) as (client, upstream):
        response = client.post("/v1/generate", json={"prompt": "hello"})

    assert response.status_code == 201
    assert response.json() == {"result": "generated"}
    assert response.headers["Content-Type"] == "application/json"
    assert response.headers["X-RateLimit-Limit"] == "5"
    assert response.headers["X-RateLimit-Remaining"] == "4"
    assert "Set-Cookie" not in response.headers
    upstream.generate.assert_awaited_once_with({"prompt": "hello"})


@pytest.mark.parametrize(
    ("upstream_error", "status_code", "detail", "private_detail"),
    [
        (
            UpstreamTimeoutError("private timeout details"),
            504,
            "Upstream request timed out",
            "private timeout details",
        ),
        (
            UpstreamTransportError("private transport details"),
            502,
            "Upstream service unavailable",
            "private transport details",
        ),
    ],
)
def test_proxy_maps_upstream_failures_without_internal_details(
    settings: Settings,
    upstream_error: Exception,
    status_code: int,
    detail: str,
    private_detail: str,
) -> None:
    with _gateway_client(settings, upstream_error) as (client, _):
        response = client.post("/v1/generate", json={"prompt": "hello"})

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    assert private_detail not in response.text
    assert response.headers["X-RateLimit-Limit"] == "5"
    assert response.headers["X-RateLimit-Remaining"] == "4"


def test_proxy_rejects_non_object_json_payload(settings: Settings) -> None:
    upstream_response = httpx.Response(200, json={"unused": True})
    with _gateway_client(settings, upstream_response) as (client, upstream):
        response = client.post("/v1/generate", json=["not", "an", "object"])

    assert response.status_code == 422
    upstream.generate.assert_not_awaited()
