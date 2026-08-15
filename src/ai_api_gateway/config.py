"""Validated application configuration."""

from typing import Annotated

from pydantic import AnyHttpUrl, Field, PostgresDsn, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded from ``GATEWAY_`` environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="GATEWAY_",
        extra="ignore",
    )

    database_dsn: PostgresDsn
    redis_url: RedisDsn
    api_key_fingerprint_pepper: Annotated[SecretStr, Field(min_length=32)]
    upstream_base_url: AnyHttpUrl
    upstream_api_key: Annotated[SecretStr, Field(min_length=1)]
    upstream_timeout_seconds: Annotated[float, Field(gt=0, le=60)] = 10.0
