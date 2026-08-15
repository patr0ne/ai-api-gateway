"""FastAPI application factory and public health endpoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ai_api_gateway.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an application whose configuration is validated at startup."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings or Settings()  # type: ignore[call-arg]
        yield

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
