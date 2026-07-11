"""Application configuration loaded from environment variables.

All settings can be overridden via environment variables (or a local .env file),
e.g. LAFZA_POSTGRES_HOST=db LAFZA_POSTGRES_PASSWORD=secret.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LAFZA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Lafza API"
    debug: bool = False

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "lafza"
    postgres_password: str = "lafza"
    postgres_db: str = "lafza"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
