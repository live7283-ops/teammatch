"""Application settings, loaded from environment (.env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://teammatch:teammatch@localhost:5432/teammatch"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 1 day

    cors_origins: list[str] = ["http://localhost:5500", "http://127.0.0.1:5500"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
