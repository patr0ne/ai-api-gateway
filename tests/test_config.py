"""Tests for environment-backed configuration validation."""

import pytest
from pydantic import ValidationError

from ai_api_gateway.config import Settings


def test_settings_load_from_prefixed_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "GATEWAY_DATABASE_DSN": ("postgresql://test_user@localhost/test_db"),
        "GATEWAY_REDIS_URL": "redis://localhost:6379/0",
        "GATEWAY_API_KEY_FINGERPRINT_PEPPER": "x" * 32,
        "GATEWAY_UPSTREAM_BASE_URL": "https://provider.invalid/v1/",
        "GATEWAY_UPSTREAM_API_KEY": "x" * 16,
        "GATEWAY_UPSTREAM_TIMEOUT_SECONDS": "2.5",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert str(settings.database_dsn).startswith("postgresql://")
    assert str(settings.redis_url) == "redis://localhost:6379/0"
    assert str(settings.upstream_base_url) == "https://provider.invalid/v1/"
    assert settings.upstream_timeout_seconds == 2.5
    assert "x" * 16 not in repr(settings)


def test_settings_reject_missing_required_values() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_settings_reject_short_fingerprint_pepper(settings: Settings) -> None:
    with pytest.raises(ValidationError):
        Settings(
            **settings.model_dump(exclude={"api_key_fingerprint_pepper"}),
            api_key_fingerprint_pepper="too-short",
            _env_file=None,
        )
