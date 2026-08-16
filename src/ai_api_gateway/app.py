"""FastAPI application factory and public health endpoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from redis.asyncio import Redis

from ai_api_gateway.config import Settings
from ai_api_gateway.database import Database
from ai_api_gateway.rate_limit import RateLimiter
from ai_api_gateway.upstream import UpstreamClient
from ai_api_gateway.upstream import router as upstream_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an application whose configuration is validated at startup."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved_settings = settings or Settings()  # type: ignore[call-arg]
        database = Database(str(resolved_settings.database_dsn))
        redis = Redis.from_url(
            str(resolved_settings.redis_url),
            decode_responses=True,
        )
        upstream_http_client = httpx.AsyncClient(
            base_url=str(resolved_settings.upstream_base_url),
            headers={
                "Authorization": (
                    f"Bearer {resolved_settings.upstream_api_key.get_secret_value()}"
                )
            },
            timeout=resolved_settings.upstream_timeout_seconds,
        )
        app.state.settings = resolved_settings
        app.state.database = database
        app.state.rate_limiter = RateLimiter(redis)
        app.state.upstream_client = UpstreamClient(upstream_http_client)
        try:
            yield
        finally:
            try:
                await upstream_http_client.aclose()
            finally:
                try:
                    await redis.aclose()
                finally:
                    await database.dispose()

    application = FastAPI(
        title="AI API Gateway",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(upstream_router)

    @application.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
