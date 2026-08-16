"""Tests for application startup, health reporting, and dependency wiring."""

from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ai_api_gateway.app import create_app
from ai_api_gateway.auth import require_api_client
from ai_api_gateway.config import Settings
from ai_api_gateway.models import ApiClient


def test_health_returns_ok(settings: Settings) -> None:
    application = create_app(settings)

    with TestClient(application) as client:
        response = client.get("/health")

        assert application.state.database.engine.url.drivername == (
            "postgresql+asyncpg"
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_startup_rejects_missing_configuration() -> None:
    with pytest.raises(ValidationError), TestClient(create_app()):
        pass


def test_protected_dependency_rejects_missing_api_key(settings: Settings) -> None:
    application = create_app(settings)

    @application.get("/protected-test")
    async def protected_test(
        client: Annotated[ApiClient, Depends(require_api_client)],
    ) -> dict[str, str]:
        return {"client": client.name}

    with TestClient(application) as client:
        response = client.get("/protected-test")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API key"}
