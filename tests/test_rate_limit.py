"""Tests for atomic Redis rate limiting and HTTP response mapping."""

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from redis.exceptions import RedisError

from ai_api_gateway.app import create_app
from ai_api_gateway.auth import require_api_client
from ai_api_gateway.config import Settings
from ai_api_gateway.models import ApiClient
from ai_api_gateway.rate_limit import (
    RATE_LIMIT_WINDOW_SECONDS,
    RateLimitDecision,
    RateLimiter,
    RateLimiterUnavailableError,
    RateLimitGrant,
    enforce_rate_limit,
)


@pytest.mark.anyio
async def test_limiter_uses_client_scoped_atomic_script() -> None:
    client_id = uuid4()
    redis = AsyncMock()
    redis.eval.return_value = [1, RATE_LIMIT_WINDOW_SECONDS]
    limiter = RateLimiter(redis)

    decision = await limiter.check(client_id)

    assert decision == RateLimitDecision(
        allowed=True,
        current=1,
        remaining=4,
        retry_after=RATE_LIMIT_WINDOW_SECONDS,
    )
    script, number_of_keys, key, window = redis.eval.await_args.args
    assert 'redis.call("INCR", KEYS[1])' in script
    assert 'redis.call("EXPIRE", KEYS[1], ARGV[1])' in script
    assert number_of_keys == 1
    assert key == f"rate_limit:{client_id}"
    assert window == RATE_LIMIT_WINDOW_SECONDS


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("current", "allowed", "remaining"),
    [(5, True, 0), (6, False, 0)],
)
async def test_fifth_attempt_is_allowed_and_sixth_is_rejected(
    current: int,
    allowed: bool,
    remaining: int,
) -> None:
    redis = AsyncMock()
    redis.eval.return_value = [current, 42]

    decision = await RateLimiter(redis).check(uuid4())

    assert decision.allowed is allowed
    assert decision.remaining == remaining
    assert decision.retry_after == 42


@pytest.mark.anyio
@pytest.mark.parametrize("result", [RedisError("down"), [1, -1]])
async def test_redis_failure_or_missing_expiry_fails_closed(result: object) -> None:
    redis = AsyncMock()
    if isinstance(result, Exception):
        redis.eval.side_effect = result
    else:
        redis.eval.return_value = result

    with pytest.raises(RateLimiterUnavailableError):
        await RateLimiter(redis).check(uuid4())


@contextmanager
def _protected_client(
    settings: Settings,
    decision: RateLimitDecision | Exception,
) -> Iterator[TestClient]:
    application = create_app(settings)
    api_client = ApiClient(
        id=uuid4(),
        name="test client",
        key_fingerprint="f" * 64,
    )

    async def authenticated_client() -> ApiClient:
        return api_client

    application.dependency_overrides[require_api_client] = authenticated_client

    @application.get("/protected-test")
    async def protected_test(
        grant: RateLimitGrant = Depends(enforce_rate_limit),
    ) -> dict[str, str]:
        return {"client": grant.client.name}

    limiter = AsyncMock(spec=RateLimiter)
    if isinstance(decision, Exception):
        limiter.check.side_effect = decision
    else:
        limiter.check.return_value = decision

    with TestClient(application) as test_client:
        application.state.rate_limiter = limiter
        yield test_client


def test_allowed_response_contains_limit_headers(settings: Settings) -> None:
    with _protected_client(
        settings,
        RateLimitDecision(True, current=1, remaining=4, retry_after=60),
    ) as client:
        response = client.get("/protected-test")

    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == "5"
    assert response.headers["X-RateLimit-Remaining"] == "4"
    assert "Retry-After" not in response.headers


def test_rejected_response_contains_retry_headers(settings: Settings) -> None:
    with _protected_client(
        settings,
        RateLimitDecision(False, current=6, remaining=0, retry_after=37),
    ) as client:
        response = client.get("/protected-test")

    assert response.status_code == 429
    assert response.json() == {"detail": "Rate limit exceeded"}
    assert response.headers["X-RateLimit-Limit"] == "5"
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert response.headers["Retry-After"] == "37"


def test_redis_failure_returns_503_without_limit_headers(settings: Settings) -> None:
    with _protected_client(settings, RateLimiterUnavailableError()) as client:
        response = client.get("/protected-test")

    assert response.status_code == 503
    assert response.json() == {"detail": "Rate limit service unavailable"}
    assert "X-RateLimit-Limit" not in response.headers
