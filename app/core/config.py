"""Typed application settings loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for uploads, processing limits, and storage."""

    # Storage backend: "sqlite" (local zero-dependency default), "memory", or "mongodb"
    db_backend: Literal["sqlite", "memory", "mongodb"] = "sqlite"
    sqlite_db_path: str = "data/geo_measurement.db"

    # Optional MongoDB settings
    mongodb_uri: str | None = None
    mongodb_db_name: str = "geo_measurement"

    # File processing constraints
    max_upload_mb: int = 50
    max_unzipped_mb: int = 500
    max_zip_entries: int = 100
    max_features_per_file: int = 50_000

    # API server settings
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = ["*"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def max_upload_bytes(self) -> int:
        """Return the maximum compressed upload size in bytes."""
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_unzipped_bytes(self) -> int:
        """Return the maximum expanded archive size in bytes."""
        return self.max_unzipped_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached process-wide settings."""
    return Settings()
