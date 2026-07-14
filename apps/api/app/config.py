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
    abuse_limits_enabled: bool = True
    trusted_proxy_cidrs: str = ""
    abuse_bucket_retention_seconds: int = 86400
    login_limit_attempts: int = 10
    login_limit_window_seconds: int = 300
    bootstrap_limit_attempts: int = 5
    bootstrap_limit_window_seconds: int = 3600
    invitation_create_limit_attempts: int = 30
    invitation_create_limit_window_seconds: int = 3600
    invitation_inspect_limit_attempts: int = 30
    invitation_inspect_limit_window_seconds: int = 300
    invitation_accept_limit_attempts: int = 10
    invitation_accept_limit_window_seconds: int = 300
    demo_access_protection_enabled: bool = False
    demo_basic_auth_username: str = ""
    demo_basic_auth_password: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    @property
    def sqlalchemy_database_url(self) -> str:
        """Use the installed psycopg v3 driver for provider-issued PostgreSQL URLs."""
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql+psycopg://", 1)
        return self.database_url

    @property
    def alembic_database_url(self) -> str:
        """Escape URL interpolation characters before passing through ConfigParser."""
        return self.sqlalchemy_database_url.replace("%", "%%")

    def validate_runtime(self) -> None:
        """Reject unsafe production settings before the application starts."""
        errors: list[str] = []
        if self.is_production:
            if self.app_secret in DEVELOPMENT_SECRETS or len(self.app_secret) < 32:
                errors.append("APP_SECRET must be a unique value with at least 32 characters")
            if not self.sqlalchemy_database_url.startswith("postgresql+psycopg://"):
                errors.append("DATABASE_URL must use PostgreSQL in production")

            origins = [item.strip() for item in self.cors_origins.split(",") if item.strip()]
            if "*" in origins:
                errors.append("CORS_ORIGINS must not contain a wildcard in production")
            for origin in origins:
                parsed = urlparse(origin)
                if parsed.scheme != "https" or not parsed.netloc:
                    errors.append("CORS_ORIGINS must contain valid HTTPS origins in production")
                    break

            if self.auto_create_schema:
                errors.append("AUTO_CREATE_SCHEMA must be false in production")
            if not self.abuse_limits_enabled:
                errors.append("ABUSE_LIMITS_ENABLED must be true in production")
            if self.demo_access_protection_enabled:
                if not self.demo_basic_auth_username.strip():
                    errors.append(
                        "DEMO_BASIC_AUTH_USERNAME is required when demo access "
                        "protection is enabled"
                    )
                if len(self.demo_basic_auth_password) < 12:
                    errors.append("DEMO_BASIC_AUTH_PASSWORD must contain at least 12 characters")

        positive_limits = {
            "ABUSE_BUCKET_RETENTION_SECONDS": self.abuse_bucket_retention_seconds,
            "LOGIN_LIMIT_ATTEMPTS": self.login_limit_attempts,
            "LOGIN_LIMIT_WINDOW_SECONDS": self.login_limit_window_seconds,
            "BOOTSTRAP_LIMIT_ATTEMPTS": self.bootstrap_limit_attempts,
            "BOOTSTRAP_LIMIT_WINDOW_SECONDS": self.bootstrap_limit_window_seconds,
            "INVITATION_CREATE_LIMIT_ATTEMPTS": self.invitation_create_limit_attempts,
            "INVITATION_CREATE_LIMIT_WINDOW_SECONDS": self.invitation_create_limit_window_seconds,
            "INVITATION_INSPECT_LIMIT_ATTEMPTS": self.invitation_inspect_limit_attempts,
            "INVITATION_INSPECT_LIMIT_WINDOW_SECONDS": self.invitation_inspect_limit_window_seconds,
            "INVITATION_ACCEPT_LIMIT_ATTEMPTS": self.invitation_accept_limit_attempts,
            "INVITATION_ACCEPT_LIMIT_WINDOW_SECONDS": self.invitation_accept_limit_window_seconds,
        }
        for name, value in positive_limits.items():
            if value <= 0:
                errors.append(f"{name} must be greater than zero")

        maximum_window = max(
            self.login_limit_window_seconds,
            self.bootstrap_limit_window_seconds,
            self.invitation_create_limit_window_seconds,
            self.invitation_inspect_limit_window_seconds,
            self.invitation_accept_limit_window_seconds,
        )
        if self.abuse_bucket_retention_seconds < maximum_window:
            errors.append(
                "ABUSE_BUCKET_RETENTION_SECONDS must be at least the longest abuse limit window"
            )

        try:
            _ = self.trusted_proxy_networks
        except ValueError:
            errors.append("TRUSTED_PROXY_CIDRS must contain valid IP networks")

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

    @property
    def trusted_proxy_networks(self):
        from ipaddress import ip_network

        return tuple(
            ip_network(item.strip(), strict=False)
            for item in self.trusted_proxy_cidrs.split(",")
            if item.strip()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
