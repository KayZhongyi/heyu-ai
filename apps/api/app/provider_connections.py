import ipaddress
import os
import re
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai import (
    AIProvider,
    AIProviderError,
    DeterministicProvider,
    GenerationResult,
    OpenAICompatibleProvider,
)
from app.config import Settings, get_settings
from app.models import ProviderConnection
from app.schemas import (
    Actor,
    ProviderConnectionCreate,
    ProviderConnectionProbe,
    ProviderConnectionUpdate,
)

SECRET_REFERENCE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
PROVIDER_TYPE = "openai-compatible"


@dataclass(frozen=True, slots=True)
class ResolvedProviderConfig:
    source: str
    name: str
    base_url: str
    api_key: str
    chat_model: str
    embedding_model: str
    timeout_seconds: float


@dataclass(slots=True)
class OrganizationFallbackProvider:
    providers: list[AIProvider]
    preflight_attempts: list[dict[str, str]] = field(default_factory=list)
    name: str = "mock"
    model: str = "deterministic-v1"
    attempts: list[dict[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.attempts = list(self.preflight_attempts)

    def generate_script(self, *args, **kwargs) -> GenerationResult:
        last_error: AIProviderError | None = None
        for provider in self.providers:
            try:
                result = provider.generate_script(*args, **kwargs)
            except AIProviderError as exc:
                self.attempts.append(
                    {
                        "provider": provider.name,
                        "model": provider.model,
                        "status": "failed",
                        "error_code": exc.code,
                        "error": str(exc),
                    }
                )
                last_error = exc
                continue
            self.name = provider.name
            self.model = provider.model
            self.attempts.append(
                {
                    "provider": provider.name,
                    "model": provider.model,
                    "status": "succeeded",
                }
            )
            return result
        if last_error is not None:
            raise last_error
        raise AIProviderError("No AI provider is available", code="provider_unavailable")


def _secret_reference_value(secret_reference: str) -> str:
    return f"env:{secret_reference}"


def _secret_reference_from_row(row: ProviderConnection) -> str:
    value = row.encrypted_api_key
    if value.startswith("env:"):
        return value.removeprefix("env:")
    return ""


def _is_blocked_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not ip.is_global


def validate_provider_url(
    base_url: str,
    settings: Settings,
    *,
    resolve_dns: bool,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> str:
    normalized = base_url.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Provider base URL must be a valid HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Provider base URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("Provider base URL must not contain a query or fragment")
    if settings.is_production and parsed.scheme != "https":
        raise ValueError("Provider base URL must use HTTPS in production")

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("Provider base URL must not target localhost")
    try:
        if _is_blocked_address(hostname):
            raise ValueError("Provider base URL must not target a private or reserved address")
    except ValueError as exc:
        if "does not appear to be" not in str(exc):
            raise

    if resolve_dns:
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            addresses = {
                item[4][0]
                for item in resolver(hostname, port)
            }
        except OSError as exc:
            raise ValueError("Provider hostname could not be resolved") from exc
        if not addresses:
            raise ValueError("Provider hostname did not resolve to an address")
        if any(_is_blocked_address(address) for address in addresses):
            raise ValueError("Provider hostname resolves to a private or reserved address")
    return normalized


def provider_connection_view(row: ProviderConnection) -> dict:
    secret_reference = _secret_reference_from_row(row)
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "name": row.name,
        "provider_type": row.provider_type,
        "base_url": row.base_url,
        "chat_model": row.chat_model,
        "embedding_model": row.embedding_model,
        "secret_reference": secret_reference,
        "secret_configured": bool(secret_reference and os.getenv(secret_reference)),
        "enabled": row.enabled,
        "is_primary": row.is_primary,
        "is_fallback": row.is_fallback,
        "last_test_status": row.last_test_status,
        "last_tested_at": row.last_tested_at,
        "last_test_error": row.last_test_error,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _validate_secret_reference(secret_reference: str) -> str:
    normalized = secret_reference.strip()
    if not SECRET_REFERENCE_PATTERN.fullmatch(normalized):
        raise HTTPException(
            status_code=422,
            detail=(
                "secret_reference must be an uppercase server environment variable name "
                "containing only letters, digits, and underscores"
            ),
        )
    return normalized


def _validate_roles(data: ProviderConnectionCreate | ProviderConnectionUpdate) -> None:
    if data.is_primary is True and data.is_fallback is True:
        raise HTTPException(
            status_code=422,
            detail="A provider connection cannot be both primary and fallback",
        )


def _tenant_connection(
    db: Session,
    actor: Actor,
    connection_id: str,
) -> ProviderConnection:
    row = db.scalar(
        select(ProviderConnection).where(
            ProviderConnection.id == connection_id,
            ProviderConnection.organization_id == actor.organization_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Provider connection not found")
    return row


def _clear_role(
    db: Session,
    organization_id: str,
    *,
    primary: bool = False,
    fallback: bool = False,
    except_id: str | None = None,
) -> None:
    statement = select(ProviderConnection).where(
        ProviderConnection.organization_id == organization_id
    )
    if except_id:
        statement = statement.where(ProviderConnection.id != except_id)
    rows = db.scalars(statement).all()
    for row in rows:
        if primary:
            row.is_primary = False
        if fallback:
            row.is_fallback = False


def list_provider_connections(db: Session, actor: Actor) -> list[ProviderConnection]:
    return list(
        db.scalars(
            select(ProviderConnection)
            .where(ProviderConnection.organization_id == actor.organization_id)
            .order_by(
                ProviderConnection.is_primary.desc(),
                ProviderConnection.is_fallback.desc(),
                ProviderConnection.created_at,
            )
        )
    )


def create_provider_connection(
    db: Session,
    actor: Actor,
    data: ProviderConnectionCreate,
    settings: Settings | None = None,
) -> ProviderConnection:
    settings = settings or get_settings()
    _validate_roles(data)
    try:
        base_url = validate_provider_url(data.base_url, settings, resolve_dns=False)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    secret_reference = _validate_secret_reference(data.secret_reference)
    if data.is_primary:
        _clear_role(db, actor.organization_id, primary=True)
    if data.is_fallback:
        _clear_role(db, actor.organization_id, fallback=True)
    row = ProviderConnection(
        organization_id=actor.organization_id,
        name=data.name.strip(),
        provider_type=PROVIDER_TYPE,
        base_url=base_url,
        chat_model=data.chat_model.strip(),
        embedding_model=data.embedding_model.strip(),
        encrypted_api_key=_secret_reference_value(secret_reference),
        enabled=data.enabled,
        is_primary=data.is_primary,
        is_fallback=data.is_fallback,
        created_by=actor.user_id,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A provider connection with this name already exists",
        ) from exc
    db.refresh(row)
    return row


def update_provider_connection(
    db: Session,
    actor: Actor,
    connection_id: str,
    data: ProviderConnectionUpdate,
    settings: Settings | None = None,
) -> ProviderConnection:
    settings = settings or get_settings()
    _validate_roles(data)
    row = _tenant_connection(db, actor, connection_id)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if "base_url" in changes:
        try:
            changes["base_url"] = validate_provider_url(
                changes["base_url"], settings, resolve_dns=False
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if "secret_reference" in changes:
        row.encrypted_api_key = _secret_reference_value(
            _validate_secret_reference(changes.pop("secret_reference"))
        )
    if changes.get("is_primary"):
        _clear_role(db, actor.organization_id, primary=True, except_id=row.id)
        row.is_fallback = False
    if changes.get("is_fallback"):
        _clear_role(db, actor.organization_id, fallback=True, except_id=row.id)
        row.is_primary = False
    for key, value in changes.items():
        if key in {"name", "chat_model", "embedding_model"}:
            value = value.strip()
        setattr(row, key, value)
    row.provider_type = PROVIDER_TYPE
    row.updated_at = datetime.now(UTC)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A provider connection with this name already exists",
        ) from exc
    db.refresh(row)
    return row


def delete_provider_connection(db: Session, actor: Actor, connection_id: str) -> None:
    row = _tenant_connection(db, actor, connection_id)
    db.delete(row)
    db.commit()


def _resolved_row(
    row: ProviderConnection,
    settings: Settings,
    *,
    capability: str,
) -> ResolvedProviderConfig:
    if row.provider_type != PROVIDER_TYPE:
        raise ValueError("Unsupported provider type")
    base_url = validate_provider_url(row.base_url, settings, resolve_dns=True)
    secret_reference = _secret_reference_from_row(row)
    if not secret_reference:
        raise ValueError("Provider connection has no server secret reference")
    api_key = os.getenv(secret_reference, "").strip()
    if not api_key:
        raise ValueError(f"Server secret {secret_reference} is not configured")
    model = row.chat_model if capability == "chat" else row.embedding_model
    if not model.strip():
        raise ValueError(f"Provider connection has no {capability} model")
    return ResolvedProviderConfig(
        source=f"organization:{row.name}",
        name=row.name,
        base_url=base_url,
        api_key=api_key,
        chat_model=row.chat_model,
        embedding_model=row.embedding_model,
        timeout_seconds=settings.ai_timeout_seconds,
    )


def resolve_organization_provider_configs(
    db: Session,
    organization_id: str,
    *,
    capability: str,
    settings: Settings | None = None,
) -> tuple[list[ResolvedProviderConfig], list[dict[str, str]]]:
    settings = settings or get_settings()
    rows = db.scalars(
        select(ProviderConnection)
        .where(
            ProviderConnection.organization_id == organization_id,
            ProviderConnection.enabled.is_(True),
        )
        .order_by(
            ProviderConnection.is_primary.desc(),
            ProviderConnection.is_fallback.desc(),
            ProviderConnection.created_at,
        )
    ).all()
    selected = [row for row in rows if row.is_primary]
    selected.extend(row for row in rows if row.is_fallback and row not in selected)
    configs: list[ResolvedProviderConfig] = []
    attempts: list[dict[str, str]] = []
    for row in selected:
        try:
            configs.append(_resolved_row(row, settings, capability=capability))
        except ValueError as exc:
            attempts.append(
                {
                    "provider": f"organization:{row.name}",
                    "model": row.chat_model if capability == "chat" else row.embedding_model,
                    "status": "unavailable",
                    "error_code": "provider_configuration_error",
                    "error": str(exc),
                }
            )
    return configs, attempts


def resolve_organization_ai_provider(
    db: Session,
    organization_id: str,
    *,
    settings: Settings | None = None,
    environment_provider: AIProvider | None = None,
) -> OrganizationFallbackProvider:
    settings = settings or get_settings()
    configs, attempts = resolve_organization_provider_configs(
        db,
        organization_id,
        capability="chat",
        settings=settings,
    )
    providers: list[AIProvider] = []
    for config in configs:
        provider = OpenAICompatibleProvider(
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.chat_model,
            timeout_seconds=config.timeout_seconds,
        )
        provider.name = config.source
        providers.append(provider)
    if environment_provider is not None:
        providers.append(environment_provider)
    else:
        from app.ai import get_ai_provider

        providers.append(get_ai_provider(settings))
    if not isinstance(providers[-1], DeterministicProvider):
        providers.append(DeterministicProvider())
    return OrganizationFallbackProvider(providers=providers, preflight_attempts=attempts)


def test_provider_connection(
    db: Session,
    actor: Actor,
    connection_id: str,
    data: ProviderConnectionProbe,
    settings: Settings | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
) -> tuple[ProviderConnection, dict]:
    settings = settings or get_settings()
    row = _tenant_connection(db, actor, connection_id)
    started = time.perf_counter()
    temporary_key = data.temporary_api_key.get_secret_value() if data.temporary_api_key else ""
    try:
        base_url = validate_provider_url(row.base_url, settings, resolve_dns=transport is None)
        secret_reference = _secret_reference_from_row(row)
        api_key = temporary_key or os.getenv(secret_reference, "").strip()
        if not api_key:
            raise ValueError("No temporary API key or configured server secret is available")
        with httpx.Client(timeout=settings.ai_timeout_seconds, transport=transport) as client:
            response = client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": row.chat_model,
                    "temperature": 0,
                    "max_tokens": 8,
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                },
            )
            response.raise_for_status()
            payload = response.json()
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or not choices:
            raise ValueError("Provider returned an invalid chat-completions response")
    except (ValueError, httpx.HTTPError) as exc:
        row.last_test_status = "failed"
        row.last_tested_at = datetime.now(UTC)
        row.last_test_error = str(exc)
        db.commit()
        return row, {
            "status": "failed",
            "provider": f"organization:{row.name}",
            "model": row.chat_model,
            "latency_ms": max(1, int((time.perf_counter() - started) * 1000)),
            "error": str(exc),
        }
    row.last_test_status = "succeeded"
    row.last_tested_at = datetime.now(UTC)
    row.last_test_error = ""
    db.commit()
    return row, {
        "status": "succeeded",
        "provider": f"organization:{row.name}",
        "model": row.chat_model,
        "latency_ms": max(1, int((time.perf_counter() - started) * 1000)),
        "error": "",
    }
