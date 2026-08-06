"""Runtime configuration.

Everything is environment driven so the same image runs in dev, staging and
production. The only value that must never be defaulted in production is
``mrn_salt`` -- it is what keeps hashed patient identifiers un-reversible.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HPF_", env_file=".env", extra="ignore")

    app_name: str = "Hospital Patient Flow & Operational Intelligence Platform"
    environment: str = "development"
    debug: bool = False

    # SQLite keeps the developer loop and the test suite dependency-free.
    # docker-compose and the Kubernetes manifests both point this at PostgreSQL.
    database_url: str = "sqlite+pysqlite:///./hpf.db"

    facility_timezone: str = "Asia/Riyadh"
    default_locale: str = "en"

    # Salt for hashing MRNs. Generated per-deployment and stored in the
    # secret manager, never in the database or the repository.
    mrn_salt: str = Field(default="dev-only-insecure-salt")

    # Uploads
    max_upload_mb: int = 100
    allowed_upload_suffixes: tuple[str, ...] = (".xlsx", ".xlsm", ".csv")
    upload_dir: str = "./var/uploads"
    model_dir: str = "./var/models"

    # A batch whose quality score falls below this is held for review
    # instead of being promoted into the warehouse.
    min_quality_score_to_load: float = 60.0

    cors_origins: tuple[str, ...] = ("http://localhost:3000",)

    @field_validator("environment")
    @classmethod
    def _known_environment(cls, value: str) -> str:
        allowed = {"development", "test", "staging", "production"}
        if value not in allowed:
            raise ValueError(f"environment must be one of {sorted(allowed)}")
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.is_production and settings.mrn_salt == "dev-only-insecure-salt":
        raise RuntimeError(
            "HPF_MRN_SALT must be set to a deployment-specific secret in production"
        )
    os.makedirs(settings.upload_dir, exist_ok=True)
    os.makedirs(settings.model_dir, exist_ok=True)
    return settings
