import os
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import AIProviderError, GenerationResult
from app.config import Settings
from app.models import ProviderConnection
from app.provider_connections import (
    OrganizationFallbackProvider,
    validate_provider_url,
)
from app.provider_connections import (
    test_provider_connection as probe_saved_connection,
)
from app.schemas import Actor, ProviderConnectionProbe
from tests.conftest import invite_and_accept


def _payload(**overrides) -> dict:
    values = {
        "name": "Domestic primary",
        "provider_type": "openai-compatible",
        "base_url": "https://api.example.com/v1",
        "chat_model": "chat-model",
        "embedding_model": "embedding-model",
        "secret_reference": "HEYU_TEST_PROVIDER_KEY",
        "enabled": True,
        "is_primary": True,
        "is_fallback": False,
    }
    values.update(overrides)
    return values


def test_owner_can_manage_metadata_without_api_key_leak(
    client: TestClient,
    auth: dict[str, str],
    db: Session,
):
    os.environ["HEYU_TEST_PROVIDER_KEY"] = "server-only-secret"
    try:
        created = client.post("/v1/provider-connections", headers=auth, json=_payload())
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["secret_reference"] == "HEYU_TEST_PROVIDER_KEY"
        assert body["secret_configured"] is True
        assert "api_key" not in body
        assert "encrypted_api_key" not in body
        assert "server-only-secret" not in created.text

        stored = db.scalar(select(ProviderConnection).where(ProviderConnection.id == body["id"]))
        assert stored is not None
        assert stored.encrypted_api_key == "env:HEYU_TEST_PROVIDER_KEY"

        listed = client.get("/v1/provider-connections", headers=auth)
        assert listed.status_code == 200
        assert listed.json() == [body]

        updated = client.patch(
            f"/v1/provider-connections/{body['id']}",
            headers=auth,
            json={"chat_model": "chat-model-v2", "is_fallback": True},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["chat_model"] == "chat-model-v2"
        assert updated.json()["is_primary"] is False
        assert updated.json()["is_fallback"] is True
    finally:
        os.environ.pop("HEYU_TEST_PROVIDER_KEY", None)


def test_provider_management_requires_owner_or_admin(
    client: TestClient,
    auth: dict[str, str],
):
    _, accepted = invite_and_accept(
        client,
        auth,
        "creator-provider@example.com",
        "creator",
        "creator-provider-password",
    )
    creator_auth = {"Authorization": f"Bearer {accepted['access_token']}"}

    assert client.get("/v1/provider-connections", headers=creator_auth).status_code == 403
    assert (
        client.post(
            "/v1/provider-connections",
            headers=creator_auth,
            json=_payload(),
        ).status_code
        == 403
    )


def test_primary_and_fallback_are_unique_per_organization(
    client: TestClient,
    auth: dict[str, str],
):
    first = client.post("/v1/provider-connections", headers=auth, json=_payload())
    assert first.status_code == 201
    second = client.post(
        "/v1/provider-connections",
        headers=auth,
        json=_payload(
            name="Second primary",
            secret_reference="HEYU_SECOND_PROVIDER_KEY",
        ),
    )
    assert second.status_code == 201

    rows = client.get("/v1/provider-connections", headers=auth).json()
    assert [row["name"] for row in rows if row["is_primary"]] == ["Second primary"]
    assert next(row for row in rows if row["name"] == "Domestic primary")["is_primary"] is False


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:11434/v1",
        "http://127.0.0.1/v1",
        "http://10.0.0.8/v1",
        "http://169.254.169.254/latest",
        "https://user:password@api.example.com/v1",
    ],
)
def test_ssrf_validation_rejects_local_private_link_local_and_credentials(url: str):
    with pytest.raises(ValueError):
        validate_provider_url(url, Settings(), resolve_dns=False)


def test_production_requires_https_provider_url():
    with pytest.raises(ValueError, match="HTTPS"):
        validate_provider_url(
            "http://api.example.com/v1",
            Settings(app_env="production"),
            resolve_dns=False,
        )


def test_dns_resolution_rejects_private_destination():
    def private_resolver(*_args):
        return [(2, 1, 6, "", ("192.168.1.20", 443))]

    with pytest.raises(ValueError, match="private or reserved"):
        validate_provider_url(
            "https://api.example.com/v1",
            Settings(),
            resolve_dns=True,
            resolver=private_resolver,
        )


def test_connection_probe_uses_temporary_key_without_persisting_it(
    client: TestClient,
    auth: dict[str, str],
    db: Session,
    owner: dict,
):
    created = client.post("/v1/provider-connections", headers=auth, json=_payload()).json()
    captured_authorization = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_authorization
        captured_authorization = request.headers["Authorization"]
        return httpx.Response(
            200,
            json={
                "id": "request-1",
                "choices": [{"message": {"role": "assistant", "content": "OK"}}],
            },
        )

    row, result = probe_saved_connection(
        db,
        Actor(
            user_id=owner["user_id"],
            organization_id=owner["organization_id"],
            role="owner",
        ),
        created["id"],
        ProviderConnectionProbe(temporary_api_key="temporary-only-secret"),
        Settings(),
        transport=httpx.MockTransport(handler),
    )

    assert result["status"] == "succeeded"
    assert captured_authorization == "Bearer temporary-only-secret"
    assert row.encrypted_api_key == "env:HEYU_TEST_PROVIDER_KEY"
    assert "temporary-only-secret" not in row.last_test_error


def test_external_provider_failure_falls_back_and_records_attempt():
    class FailingProvider:
        name = "organization:primary"
        model = "primary-model"

        def generate_script(self, *_args, **_kwargs):
            raise AIProviderError("upstream unavailable", code="provider_connection_error")

    class SuccessfulProvider:
        name = "environment-provider"
        model = "environment-model"

        def generate_script(self, *_args, **_kwargs):
            return GenerationResult(content={"ok": True}, latency_ms=4)

    provider = OrganizationFallbackProvider(
        providers=[FailingProvider(), SuccessfulProvider()],
        preflight_attempts=[
            {
                "provider": "organization:fallback",
                "model": "fallback-model",
                "status": "unavailable",
                "error_code": "provider_configuration_error",
                "error": "Server secret is not configured",
            }
        ],
    )
    result = provider.generate_script(
        SimpleNamespace(),
        SimpleNamespace(),
        SimpleNamespace(),
        [],
    )

    assert result.content == {"ok": True}
    assert provider.name == "environment-provider"
    assert provider.model == "environment-model"
    assert provider.attempts == [
        {
            "provider": "organization:fallback",
            "model": "fallback-model",
            "status": "unavailable",
            "error_code": "provider_configuration_error",
            "error": "Server secret is not configured",
        },
        {
            "provider": "organization:primary",
            "model": "primary-model",
            "status": "failed",
            "error_code": "provider_connection_error",
            "error": "upstream unavailable",
        },
        {
            "provider": "environment-provider",
            "model": "environment-model",
            "status": "succeeded",
        },
    ]
