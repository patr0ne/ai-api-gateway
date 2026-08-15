"""Shared test fixtures."""

import pytest

from ai_api_gateway.config import Settings


@pytest.fixture(autouse=True)
def clear_gateway_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests independent from a developer's local gateway environment."""

    for field_name in Settings.model_fields:
        monkeypatch.delenv(f"GATEWAY_{field_name.upper()}", raising=False)


@pytest.fixture
def settings() -> Settings:
    """Return a complete configuration made only from test values."""

    return Settings(
        database_dsn="postgresql://test_user@localhost/test_db",
        redis_url="redis://localhost:6379/0",
        api_key_fingerprint_pepper="x" * 32,
        upstream_base_url="https://provider.invalid/v1/",
        upstream_api_key="x" * 16,
        _env_file=None,
    )
