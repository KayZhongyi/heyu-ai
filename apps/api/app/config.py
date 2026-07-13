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
    ai_base_url: str = ""
    ai_api_key: str = ""
    ai_timeout_seconds: float = 45.0
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

        provider = self.ai_provider.strip().lower()
        if provider not in {"mock", "openai-compatible"}:
            errors.append("AI_PROVIDER must be mock or openai-compatible")
        if provider == "openai-compatible":
            parsed = urlparse(self.ai_base_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                errors.append("AI_BASE_URL must be a valid HTTP(S) URL")
            if not self.ai_model.strip():
                errors.append("AI_MODEL is required for openai-compatible")
            if not self.ai_api_key.strip():
                errors.append("AI_API_KEY is required for openai-compatible")
            if self.ai_timeout_seconds <= 0 or self.ai_timeout_seconds > 300:
                errors.append("AI_TIMEOUT_SECONDS must be between 0 and 300")

        if errors:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(errors))


@lru_cache
def get_settings() -> Settings:
    return Settings()
