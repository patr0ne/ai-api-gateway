"""Atomic Redis-backed per-client rate limiting."""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Response, status
from redis.asyncio import Redis
from redis.exceptions import RedisError

from ai_api_gateway.auth import require_api_client
from ai_api_gateway.models import ApiClient

RATE_LIMIT = 5
RATE_LIMIT_WINDOW_SECONDS = 60

_FIXED_WINDOW_SCRIPT = """
local current = redis.call("INCR", KEYS[1])
if current == 1 then
    redis.call("EXPIRE", KEYS[1], ARGV[1])
end
local ttl = redis.call("TTL", KEYS[1])
return {current, ttl}
"""


class RateLimiterUnavailableError(RuntimeError):
    """Raised when Redis cannot make a safe rate-limit decision."""


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """The result of one atomic fixed-window increment."""

    allowed: bool
    current: int
    remaining: int
    retry_after: int

    def headers(self, *, include_retry_after: bool = False) -> dict[str, str]:
        headers = {
            "X-RateLimit-Limit": str(RATE_LIMIT),
            "X-RateLimit-Remaining": str(self.remaining),
        }
        if include_retry_after:
            headers["Retry-After"] = str(self.retry_after)
        return headers


@dataclass(frozen=True, slots=True)
class RateLimitGrant:
    """An authenticated client and the rate-limit decision for its request."""

    client: ApiClient
    decision: RateLimitDecision


class RateLimiter:
    """Apply the shared fixed-window algorithm through one Redis client."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def check(self, client_id: UUID) -> RateLimitDecision:
        key = f"rate_limit:{client_id}"
        try:
            result = await self._redis.eval(
                _FIXED_WINDOW_SCRIPT,
                1,
                key,
                RATE_LIMIT_WINDOW_SECONDS,
            )
            current, ttl = (int(value) for value in result)
        except (RedisError, TypeError, ValueError) as exc:
            raise RateLimiterUnavailableError from exc

        if current < 1 or ttl < 0:
            raise RateLimiterUnavailableError

        return RateLimitDecision(
            allowed=current <= RATE_LIMIT,
            current=current,
            remaining=max(0, RATE_LIMIT - current),
            retry_after=ttl,
        )


async def enforce_rate_limit(
    request: Request,
    response: Response,
    client: Annotated[ApiClient, Depends(require_api_client)],
) -> RateLimitGrant:
    """Authenticate a client, consume one attempt, and expose limit headers."""

    limiter: RateLimiter = request.app.state.rate_limiter
    try:
        decision = await limiter.check(client.id)
    except RateLimiterUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limit service unavailable",
        ) from exc

    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers=decision.headers(include_retry_after=True),
        )

    response.headers.update(decision.headers())
    return RateLimitGrant(client=client, decision=decision)
