"""Atomic rate-limiter integration tests against a real Redis service."""

import asyncio
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from ai_api_gateway.rate_limit import RateLimiter

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def test_real_redis_limits_clients_independently_and_resets(
    redis_client: Redis,
) -> None:
    limiter = RateLimiter(redis_client)
    first_client = uuid4()
    second_client = uuid4()

    decisions = [await limiter.check(first_client) for _ in range(6)]

    assert [decision.allowed for decision in decisions] == [
        True,
        True,
        True,
        True,
        True,
        False,
    ]
    assert [decision.remaining for decision in decisions] == [4, 3, 2, 1, 0, 0]

    independent = await limiter.check(second_client)
    assert independent.allowed is True
    assert independent.current == 1

    await redis_client.expire(f"rate_limit:{first_client}", 1)
    await asyncio.sleep(1.1)
    reset = await limiter.check(first_client)
    assert reset.allowed is True
    assert reset.current == 1
    assert reset.remaining == 4


async def test_concurrent_requests_cannot_bypass_real_redis_limit(
    redis_client: Redis,
) -> None:
    limiter = RateLimiter(redis_client)
    client_id = uuid4()

    decisions = await asyncio.gather(*(limiter.check(client_id) for _ in range(10)))

    assert sum(decision.allowed for decision in decisions) == 5
    assert sorted(decision.current for decision in decisions) == list(range(1, 11))
