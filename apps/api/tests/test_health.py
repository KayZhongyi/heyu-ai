from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

from app.config import Settings
from app.main import find_web_dir


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
    )

    with pytest.raises(RuntimeError) as error:
        settings.validate_runtime()

    message = str(error.value)
    assert "APP_SECRET" in message
    assert "PostgreSQL" in message
    assert "CORS_ORIGINS" in message
    assert "AUTO_CREATE_SCHEMA" in message


def test_production_settings_accept_explicit_secure_values():
    Settings(
        app_env="production",
        app_secret="a-unique-production-secret-with-more-than-32-characters",
        database_url="postgresql+psycopg://app:secret@db:5432/heyu",
        cors_origins="https://heyu.example,https://admin.heyu.example",
        auto_create_schema=False,
    ).validate_runtime()


def test_development_settings_keep_zero_cost_defaults():
    Settings().validate_runtime()


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
    assert "禾语 AI" in response.text
    assert "让土地里的认真" in response.text
    assert "hero-field-fallback.svg" in response.text
    assert 'href="/workspace/"' in response.text

    workspace = client.get("/workspace/studio")
    assert workspace.status_code == 200
    assert 'id="bootstrap-form"' in workspace.text
    assert 'data-page-panel="studio"' in workspace.text

    missing_page = client.get("/workspace/not-a-module")
    assert missing_page.status_code == 404
    assert missing_page.json()["detail"] == "Workspace page not found."

    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert "bootstrap-form" in asset.text


def test_workspace_files_are_utf8(client):
    response = client.get("/")
    assert response.encoding == "utf-8"
    assert "让土地里的认真" in response.text

    workspace = client.get("/workspace/")
    assert workspace.encoding == "utf-8"
    assert "进入禾语内容工作台" in workspace.text


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
