"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    database_url: str | None = None

    # Authentication settings
    jwt_secret_key: SecretStr | None = None
    jwt_access_token_expire_minutes: int = Field(
        default=30,
        ge=1,
        le=1440,
    )

    # AI provider settings
    ai_provider: Literal["disabled", "openai_compatible"] = "disabled"
    ai_api_key: SecretStr | None = None
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str | None = None
    ai_timeout_seconds: float = Field(
        default=30.0,
        ge=1.0,
        le=120.0,
    )
    ai_max_output_tokens: int = Field(
        default=1800,
        ge=128,
        le=8192,
    )

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()