from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "development"
    app_log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"

    database_url: str = Field(..., alias="DATABASE_URL")
    redis_url: str = Field("redis://redis:6379/0", alias="REDIS_URL")

    s3_endpoint: str = Field(..., alias="S3_ENDPOINT")
    s3_public_endpoint: str = Field("", alias="S3_PUBLIC_ENDPOINT")
    s3_access_key: str = Field(..., alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field(..., alias="S3_SECRET_KEY")
    s3_bucket: str = Field(..., alias="S3_BUCKET")
    s3_region: str = Field("me-south-1", alias="S3_REGION")

    jwt_secret: str = Field(..., alias="JWT_SECRET")
    jwt_alg: str = Field("HS256", alias="JWT_ALG")
    jwt_access_ttl_min: int = Field(60, alias="JWT_ACCESS_TTL_MIN")
    jwt_refresh_ttl_days: int = Field(14, alias="JWT_REFRESH_TTL_DAYS")

    openai_api_key: str = Field("", alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field("", alias="ANTHROPIC_API_KEY")
    vision_model: str = Field("gpt-4o", alias="VISION_MODEL")
    text_model: str = Field("claude-3-5-sonnet-latest", alias="TEXT_MODEL")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
