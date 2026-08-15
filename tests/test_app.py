"""Tests for application startup and health reporting."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ai_api_gateway.app import create_app
from ai_api_gateway.config import Settings


def test_health_returns_ok(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_startup_rejects_missing_configuration() -> None:
    with pytest.raises(ValidationError), TestClient(create_app()):
        pass
