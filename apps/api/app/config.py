from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_secret: str = "local-development-secret"
    database_url: str = "sqlite:///./agri_content.db"
    ai_provider: str = "mock"
    ai_model: str = "deterministic-v1"
    cors_origins: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
