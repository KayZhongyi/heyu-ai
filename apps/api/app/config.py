from functools import lru_cache
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

DEVELOPMENT_SECRETS = {
    "local-development-secret",
    "replace-this-in-production",
}


class Settings(BaseSettings):
    app_env: str = "development"
    app_secret: str = "local-development-secret"
    database_url: str = "sqlite:///./agri_content.db"
    ai_provider: str = "mock"
    ai_model: str = "deterministic-v1"
    cors_origins: str = "http://localhost:3000"
    auto_create_schema: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    def validate_runtime(self) -> None:
        """Reject unsafe production settings before the application starts."""
        errors: list[str] = []
        if self.is_production:
            if self.app_secret in DEVELOPMENT_SECRETS or len(self.app_secret) < 32:
                errors.append("APP_SECRET must be a unique value with at least 32 characters")
            if self.database_url.startswith("sqlite"):
                errors.append("DATABASE_URL must use PostgreSQL in production")

            origins = [item.strip() for item in self.cors_origins.split(",") if item.strip()]
            if not origins or "*" in origins:
                errors.append("CORS_ORIGINS must explicitly list trusted origins")
            for origin in origins:
                parsed = urlparse(origin)
                if parsed.scheme != "https" or not parsed.netloc:
                    errors.append("CORS_ORIGINS must contain valid HTTPS origins in production")
                    break

            if self.auto_create_schema:
                errors.append("AUTO_CREATE_SCHEMA must be false in production")

        if errors:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(errors))


@lru_cache
def get_settings() -> Settings:
    return Settings()
