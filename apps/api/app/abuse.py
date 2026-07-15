import hashlib
import hmac
import ipaddress
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request, status
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AbuseLimitBucket


def normalize_identifier(value: str) -> str:
    return value.strip().casefold()


def client_network_identity(request: Request, settings: Settings) -> str:
    """Return a client address without trusting caller-controlled forwarding headers."""
    peer = request.client.host if request.client else "unknown"
    try:
        current = ipaddress.ip_address(peer)
    except ValueError:
        return peer

    if not any(current in network for network in settings.trusted_proxy_networks):
        return current.compressed

    forwarded = request.headers.get("x-forwarded-for", "")
    candidates = [item.strip() for item in forwarded.split(",") if item.strip()]
    for raw_candidate in reversed(candidates):
        try:
            candidate = ipaddress.ip_address(raw_candidate)
        except ValueError:
            return current.compressed
        current = candidate
        if not any(current in network for network in settings.trusted_proxy_networks):
            break
    return current.compressed


def protected_subject(settings: Settings, *parts: str) -> str:
    normalized = "\x1f".join(parts)
    return hmac.new(
        settings.app_secret.encode("utf-8"),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _window_start(now: datetime, window_seconds: int) -> datetime:
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % window_seconds), tz=UTC)


def enforce_limit(
    db: Session,
    settings: Settings,
    *,
    scope: str,
    subjects: list[str],
    attempts: int,
    window_seconds: int,
    now: datetime | None = None,
) -> None:
    """Consume fixed-window limits in the primary database.

    Subjects are HMAC-protected before storage. Each subject is checked independently,
    allowing a route to enforce both a network-wide and a target-specific limit.
    """
    if not settings.abuse_limits_enabled:
        return

    current_time = now or datetime.now(UTC)
    window_started_at = _window_start(current_time, window_seconds)
    retry_after = max(
        1,
        int((window_started_at + timedelta(seconds=window_seconds) - current_time).total_seconds())
        + 1,
    )

    subject_hashes = [protected_subject(settings, subject) for subject in dict.fromkeys(subjects)]
    # The limiter owns a short, independent transaction. It must never commit or
    # roll back business objects staged by the request handler's session.
    with Session(bind=db.get_bind()) as limiter_db:
        dialect_name = limiter_db.get_bind().dialect.name
        insert_factory: Any
        if dialect_name == "postgresql":
            insert_factory = postgresql_insert
        elif dialect_name == "sqlite":
            insert_factory = sqlite_insert
        else:
            raise RuntimeError(f"Unsupported database dialect for abuse controls: {dialect_name}")

        for subject_hash in subject_hashes:
            statement = insert_factory(AbuseLimitBucket).values(
                scope=scope,
                subject_hash=subject_hash,
                window_started_at=window_started_at,
                request_count=1,
                updated_at=current_time,
            )
            statement = statement.on_conflict_do_update(
                index_elements=[
                    AbuseLimitBucket.scope,
                    AbuseLimitBucket.subject_hash,
                    AbuseLimitBucket.window_started_at,
                ],
                set_={
                    "request_count": AbuseLimitBucket.request_count + 1,
                    "updated_at": current_time,
                },
                where=AbuseLimitBucket.request_count < attempts,
            ).returning(AbuseLimitBucket.request_count)
            consumed_count = limiter_db.scalar(statement)
            if consumed_count is None:
                limiter_db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please try again later.",
                    headers={
                        "Retry-After": str(retry_after),
                        "Cache-Control": "no-store",
                    },
                )
        limiter_db.commit()

        cutoff = current_time - timedelta(seconds=settings.abuse_bucket_retention_seconds)
        # Keep request latency predictable: cleanup is only attempted periodically.
        if int(current_time.timestamp()) % 64 == 0:
            limiter_db.execute(delete(AbuseLimitBucket).where(AbuseLimitBucket.updated_at < cutoff))
            limiter_db.commit()


def network_subject(request: Request, settings: Settings) -> str:
    return f"network:{client_network_identity(request, settings)}"
