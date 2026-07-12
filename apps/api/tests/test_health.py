from pathlib import Path

from app.main import find_web_dir


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_workspace_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "禾语 AI" in response.text

    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert "bootstrap-form" in asset.text


def test_workspace_files_are_utf8(client):
    response = client.get("/")
    assert response.encoding == "utf-8"
    assert "让真实农产品" in response.text


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
