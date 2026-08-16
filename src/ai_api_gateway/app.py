"""FastAPI application factory and public health endpoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from ai_api_gateway.config import Settings
from ai_api_gateway.database import Database
from ai_api_gateway.rate_limit import RateLimiter


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
        app.state.settings = resolved_settings
        app.state.database = database
        app.state.rate_limiter = RateLimiter(redis)
        try:
            yield
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

    @application.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
