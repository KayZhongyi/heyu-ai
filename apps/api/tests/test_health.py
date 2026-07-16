import base64
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

from app.config import Settings, get_settings
from app.main import find_web_dir, valid_demo_basic_authorization


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_checks_database(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_when_database_is_unavailable(client, db, monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise OperationalError("SELECT 1", {}, RuntimeError("offline"))

    monkeypatch.setattr(db, "execute", unavailable)
    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database is not ready."}


def test_production_settings_require_secure_runtime_values():
    settings = Settings(
        app_env="production",
        app_secret="local-development-secret",
        database_url="sqlite:///./heyu.db",
        cors_origins="*",
        auto_create_schema=True,
        abuse_limits_enabled=False,
    )

    with pytest.raises(RuntimeError) as error:
        settings.validate_runtime()

    message = str(error.value)
    assert "APP_SECRET" in message
    assert "PostgreSQL" in message
    assert "CORS_ORIGINS" in message
    assert "AUTO_CREATE_SCHEMA" in message
    assert "ABUSE_LIMITS_ENABLED" in message


def test_production_settings_accept_explicit_secure_values():
    Settings(
        app_env="production",
        app_secret="a-unique-production-secret-with-more-than-32-characters",
        database_url="postgresql+psycopg://app:secret@db:5432/heyu",
        cors_origins="https://heyu.example,https://admin.heyu.example",
        auto_create_schema=False,
    ).validate_runtime()


def test_production_settings_allow_same_origin_only_cors():
    Settings(
        app_env="production",
        app_secret="a-unique-production-secret-with-more-than-32-characters",
        database_url="postgresql+psycopg://app:secret@db:5432/heyu",
        cors_origins="",
        auto_create_schema=False,
    ).validate_runtime()


@pytest.mark.parametrize(
    ("provider_url", "sqlalchemy_url"),
    [
        (
            "postgresql://app:secret@db:5432/heyu",
            "postgresql+psycopg://app:secret@db:5432/heyu",
        ),
        (
            "postgres://app:secret@db:5432/heyu",
            "postgresql+psycopg://app:secret@db:5432/heyu",
        ),
    ],
)
def test_provider_postgresql_urls_select_installed_psycopg_driver(provider_url, sqlalchemy_url):
    assert Settings(database_url=provider_url).sqlalchemy_database_url == sqlalchemy_url


def test_alembic_url_escapes_provider_percent_encoding():
    settings = Settings(database_url="postgresql://app:p%40ss@db:5432/heyu")
    assert settings.alembic_database_url == ("postgresql+psycopg://app:p%%40ss@db:5432/heyu")


def test_production_settings_reject_non_postgresql_database():
    settings = Settings(
        app_env="production",
        app_secret="a-unique-production-secret-with-more-than-32-characters",
        database_url="mysql://app:secret@db:3306/heyu",
        cors_origins="",
        auto_create_schema=False,
    )
    with pytest.raises(RuntimeError, match="DATABASE_URL must use PostgreSQL"):
        settings.validate_runtime()


def test_demo_access_protection_requires_strong_credentials():
    settings = Settings(
        app_env="production",
        app_secret="a-unique-production-secret-with-more-than-32-characters",
        database_url="postgresql://app:secret@db:5432/heyu",
        cors_origins="",
        auto_create_schema=False,
        demo_access_protection_enabled=True,
        demo_basic_auth_username="",
        demo_basic_auth_password="short",
    )
    with pytest.raises(RuntimeError) as error:
        settings.validate_runtime()
    assert "DEMO_BASIC_AUTH_USERNAME" in str(error.value)
    assert "DEMO_BASIC_AUTH_PASSWORD" in str(error.value)


def test_demo_basic_authorization_uses_constant_value_comparison():
    settings = Settings(
        demo_basic_auth_username="heyu-demo",
        demo_basic_auth_password="a-long-demo-password",
    )
    valid = base64.b64encode(b"heyu-demo:a-long-demo-password").decode()
    invalid = base64.b64encode(b"heyu-demo:wrong-password").decode()
    assert valid_demo_basic_authorization(f"Basic {valid}", settings)
    assert not valid_demo_basic_authorization(f"Basic {invalid}", settings)
    assert not valid_demo_basic_authorization("Basic not-base64", settings)
    assert not valid_demo_basic_authorization("Bearer token", settings)


def test_demo_access_middleware_protects_public_surfaces_and_bootstrap(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "demo_access_protection_enabled", True)
    monkeypatch.setattr(settings, "demo_basic_auth_username", "heyu-demo")
    monkeypatch.setattr(settings, "demo_basic_auth_password", "a-long-demo-password")

    denied_page = client.get("/")
    assert denied_page.status_code == 401
    assert denied_page.headers["www-authenticate"].startswith("Basic ")
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200

    denied_bootstrap = client.post(
        "/v1/auth/bootstrap",
        json={
            "organization_name": "Protected Demo",
            "organization_slug": "protected-demo",
            "email": "owner@protected.example",
            "display_name": "Protected Owner",
            "password": "SecurePassword2026!",
        },
    )
    assert denied_bootstrap.status_code == 401

    credentials = base64.b64encode(b"heyu-demo:a-long-demo-password").decode()
    allowed_page = client.get("/", headers={"Authorization": f"Basic {credentials}"})
    assert allowed_page.status_code == 200

    spoofed_bootstrap = client.post(
        "/v1/auth/bootstrap",
        headers={"Authorization": "Bearer not-a-real-token"},
        json={
            "organization_name": "Spoofed Demo",
            "organization_slug": "spoofed-demo",
            "email": "owner@spoofed.example",
            "display_name": "Spoofed Owner",
            "password": "SecurePassword2026!",
        },
    )
    assert spoofed_bootstrap.status_code == 401

    bootstrap = client.post(
        "/v1/auth/bootstrap",
        headers={"Authorization": f"Basic {credentials}"},
        json={
            "organization_name": "Protected Demo",
            "organization_slug": "protected-demo",
            "email": "owner@protected.example",
            "display_name": "Protected Owner",
            "password": "SecurePassword2026!",
        },
    )
    assert bootstrap.status_code == 201
    actor = client.get(
        "/v1/me",
        headers={"Authorization": f"Bearer {bootstrap.json()['access_token']}"},
    )
    assert actor.status_code == 200
    assert actor.json()["role"] == "owner"


def test_development_settings_keep_zero_cost_defaults():
    Settings().validate_runtime()


def test_abuse_settings_reject_invalid_limits_and_proxy_networks():
    settings = Settings(
        login_limit_attempts=0,
        trusted_proxy_cidrs="not-a-network",
        abuse_bucket_retention_seconds=60,
    )
    with pytest.raises(RuntimeError) as error:
        settings.validate_runtime()
    message = str(error.value)
    assert "LOGIN_LIMIT_ATTEMPTS" in message
    assert "TRUSTED_PROXY_CIDRS" in message
    assert "ABUSE_BUCKET_RETENTION_SECONDS" in message


def test_openai_compatible_settings_require_explicit_connection_values():
    settings = Settings(
        ai_provider="openai-compatible",
        ai_base_url="",
        ai_api_key="",
        ai_model="",
    )
    with pytest.raises(RuntimeError) as exc:
        settings.validate_runtime()
    assert "AI_BASE_URL" in str(exc.value)
    assert "AI_API_KEY" in str(exc.value)
    assert "AI_MODEL" in str(exc.value)


def test_openai_compatible_settings_accept_valid_values():
    Settings(
        ai_provider="openai-compatible",
        ai_base_url="https://model.example/v1",
        ai_api_key="user-provided-key",
        ai_model="example-model",
        ai_timeout_seconds=30,
    ).validate_runtime()


def test_login_accepts_organization_slug(client):
    bootstrap = client.post(
        "/v1/auth/bootstrap",
        json={
            "organization_name": "Slug Login Team",
            "organization_slug": "slug-login-team",
            "email": "slug-login@example.com",
            "display_name": "Owner",
            "password": "SecurePassword2026!",
        },
    )
    assert bootstrap.status_code == 201

    login = client.post(
        "/v1/auth/login",
        json={
            "organization_slug": "slug-login-team",
            "email": "slug-login@example.com",
            "password": "SecurePassword2026!",
        },
    )

    assert login.status_code == 200
    assert login.json()["organization_id"] == bootstrap.json()["organization_id"]


def test_landing_and_workspace_are_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "\u79be\u8bed AI" in response.text
    assert "\u8ba9\u597d\u4ea7\u54c1\u8d70\u5411\u5e02\u573a" in response.text
    assert "hero-field-fallback.svg" in response.text
    assert 'href="/workspace/"' in response.text

    workspace = client.get("/workspace/studio")
    assert workspace.status_code == 200
    assert 'id="bootstrap-form"' in workspace.text
    assert 'data-page-panel="studio"' in workspace.text

    campaigns = client.get("/workspace/campaigns")
    assert campaigns.status_code == 200
    assert 'data-page-panel="campaigns"' in campaigns.text

    missing_page = client.get("/workspace/not-a-module")
    assert missing_page.status_code == 404
    assert missing_page.json()["detail"] == "Workspace page not found."

    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert "bootstrap-form" in asset.text


def test_workspace_files_are_utf8(client):
    response = client.get("/")
    assert response.encoding == "utf-8"
    assert "\u8ba9\u597d\u4ea7\u54c1\u8d70\u5411\u5e02\u573a" in response.text

    workspace = client.get("/workspace/")
    assert workspace.encoding == "utf-8"
    assert 'id="workspace"' in workspace.text


def test_find_web_dir_supports_repository_layout(tmp_path: Path):
    module = tmp_path / "apps" / "api" / "app" / "main.py"
    web = tmp_path / "apps" / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("ok", encoding="utf-8")

    assert find_web_dir(module) == web


def test_find_web_dir_supports_container_layout(tmp_path: Path):
    module = tmp_path / "app" / "main.py"
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("ok", encoding="utf-8")

    assert find_web_dir(module) == web
