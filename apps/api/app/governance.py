from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.media_analysis import VIDEO_STORAGE_ENV
from app.models import (
    BackgroundTask,
    MediaAsset,
    Organization,
    OrganizationDataPolicy,
    PlatformExportPackage,
    ProviderConnection,
    Role,
    utc_now,
)
from app.publication_workflow import DEFAULT_STORAGE_ENV
from app.schemas import Actor

DEFAULT_MEDIA_RETENTION_DAYS = 90
DEFAULT_EXPORT_RETENTION_DAYS = 30
DEFAULT_GENERATION_LOG_RETENTION_DAYS = 365

RETENTION_LIMITS = {
    "media_retention_days": (1, 3650),
    "export_retention_days": (1, 365),
    "generation_log_retention_days": (7, 3650),
}
ADMIN_ROLES = frozenset({Role.owner, Role.admin})


@dataclass(frozen=True, slots=True)
class DataPolicyUpdate:
    media_retention_days: int = DEFAULT_MEDIA_RETENTION_DAYS
    export_retention_days: int = DEFAULT_EXPORT_RETENTION_DAYS
    generation_log_retention_days: int = DEFAULT_GENERATION_LOG_RETENTION_DAYS
    allow_model_training: bool = False


@dataclass(frozen=True, slots=True)
class CleanupItem:
    record_type: str
    record_id: str
    storage_key: str
    database_status: str
    file_result: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class CleanupReport:
    organization_id: str
    started_at: datetime
    finished_at: datetime
    media: tuple[CleanupItem, ...]
    export_packages: tuple[CleanupItem, ...]

    @property
    def deleted_files(self) -> int:
        return sum(item.file_result == "deleted" for item in (*self.media, *self.export_packages))

    @property
    def failed_records(self) -> int:
        return sum(
            item.database_status == "cleanup_failed"
            for item in (*self.media, *self.export_packages)
        )


def require_governance_admin(actor: Actor) -> None:
    if actor.role not in ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner or admin role required",
        )


def get_data_policy(db: Session, actor: Actor) -> OrganizationDataPolicy:
    require_governance_admin(actor)
    policy = db.get(OrganizationDataPolicy, actor.organization_id)
    if policy is not None:
        return policy
    policy = OrganizationDataPolicy(
        organization_id=actor.organization_id,
        media_retention_days=DEFAULT_MEDIA_RETENTION_DAYS,
        export_retention_days=DEFAULT_EXPORT_RETENTION_DAYS,
        generation_log_retention_days=DEFAULT_GENERATION_LOG_RETENTION_DAYS,
        allow_model_training=False,
        updated_by=actor.user_id,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


def update_data_policy(
    db: Session,
    actor: Actor,
    data: DataPolicyUpdate,
) -> OrganizationDataPolicy:
    require_governance_admin(actor)
    _validate_policy(data)
    policy = db.get(OrganizationDataPolicy, actor.organization_id)
    if policy is None:
        policy = OrganizationDataPolicy(
            organization_id=actor.organization_id,
            updated_by=actor.user_id,
        )
        db.add(policy)
    policy.media_retention_days = data.media_retention_days
    policy.export_retention_days = data.export_retention_days
    policy.generation_log_retention_days = data.generation_log_retention_days
    policy.allow_model_training = data.allow_model_training
    policy.updated_by = actor.user_id
    policy.updated_at = utc_now()
    db.commit()
    db.refresh(policy)
    return policy


def cleanup_expired_storage(
    db: Session,
    actor: Actor,
    *,
    media_storage_root: str | Path | None = None,
    export_storage_root: str | Path | None = None,
    now: datetime | None = None,
) -> CleanupReport:
    require_governance_admin(actor)
    started_at = _aware(now or utc_now())
    policy = get_data_policy(db, actor)
    media_cutoff = started_at - timedelta(days=policy.media_retention_days)
    export_cutoff = started_at - timedelta(days=policy.export_retention_days)
    media_root = _storage_root(
        media_storage_root,
        env_name=VIDEO_STORAGE_ENV,
        default=Path.cwd() / "private" / "videos",
    )
    export_root = _storage_root(
        export_storage_root,
        env_name=DEFAULT_STORAGE_ENV,
        default=Path.cwd() / "private" / "platform-exports",
    )

    media_rows = db.scalars(
        select(MediaAsset).where(
            MediaAsset.organization_id == actor.organization_id,
            MediaAsset.deleted_at.is_(None),
        )
    ).all()
    package_rows = db.scalars(
        select(PlatformExportPackage).where(
            PlatformExportPackage.organization_id == actor.organization_id
        )
    ).all()

    media_results = [
        _cleanup_media(db, row, media_root, actor, started_at)
        for row in media_rows
        if _is_expired(row.expires_at, row.created_at, media_cutoff, started_at)
    ]
    package_results = [
        _cleanup_export_package(db, row, export_root, actor, started_at)
        for row in package_rows
        if not _export_cleanup_recorded(row)
        and _is_expired(row.expires_at, row.created_at, export_cutoff, started_at)
    ]
    db.commit()
    return CleanupReport(
        organization_id=actor.organization_id,
        started_at=started_at,
        finished_at=utc_now(),
        media=tuple(media_results),
        export_packages=tuple(package_results),
    )


def export_organization_data(db: Session, actor: Actor) -> dict[str, Any]:
    require_governance_admin(actor)
    organization = db.scalar(select(Organization).where(Organization.id == actor.organization_id))
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    policy = get_data_policy(db, actor)
    media = _tenant_rows(db, MediaAsset, actor.organization_id)
    packages = _tenant_rows(db, PlatformExportPackage, actor.organization_id)
    providers = _tenant_rows(db, ProviderConnection, actor.organization_id)
    tasks = _tenant_rows(db, BackgroundTask, actor.organization_id)
    return {
        "schema_version": "organization-governance-export-v1",
        "exported_at": utc_now().isoformat(),
        "organization": _record(organization),
        "data_policy": _record(policy),
        "media_assets": [_record(row) for row in media],
        "platform_export_packages": [_record(row) for row in packages],
        "provider_connections": [_provider_record(row) for row in providers],
        "background_tasks": [_record(row) for row in tasks],
    }


def export_organization_data_json(db: Session, actor: Actor) -> bytes:
    payload = export_organization_data(db, actor)
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def get_system_health(db: Session, actor: Actor) -> dict[str, Any]:
    require_governance_admin(actor)
    checked_at = utc_now()
    database_status = "ok"
    database_error = ""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - exercised through a fake session
        database_status = "error"
        database_error = type(exc).__name__
        return {
            "checked_at": checked_at.isoformat(),
            "organization_id": actor.organization_id,
            "database": {
                "status": database_status,
                "error_type": database_error,
            },
            "providers": {
                "status": "unavailable",
                "reason": "database_query_unavailable",
            },
            "background_tasks": {
                "status": "unavailable",
                "reason": "database_query_unavailable",
            },
        }

    providers = _tenant_rows(db, ProviderConnection, actor.organization_id)
    tasks = _tenant_rows(db, BackgroundTask, actor.organization_id)
    provider_statuses = Counter(row.last_test_status or "unknown" for row in providers)
    task_statuses = Counter(row.status or "unknown" for row in tasks)
    overdue_leases = sum(
        row.status == "running"
        and row.lease_expires_at is not None
        and _aware(row.lease_expires_at) <= checked_at
        for row in tasks
    )
    return {
        "checked_at": checked_at.isoformat(),
        "organization_id": actor.organization_id,
        "database": {
            "status": database_status,
            "error_type": database_error,
        },
        "providers": {
            "total": len(providers),
            "enabled": sum(row.enabled for row in providers),
            "primary": sum(row.is_primary for row in providers),
            "fallback": sum(row.is_fallback for row in providers),
            "last_test_status_counts": dict(sorted(provider_statuses.items())),
            "never_tested": sum(row.last_tested_at is None for row in providers),
        },
        "background_tasks": {
            "total": len(tasks),
            "status_counts": dict(sorted(task_statuses.items())),
            "overdue_running_leases": overdue_leases,
        },
    }


def _validate_policy(data: DataPolicyUpdate) -> None:
    for field_name, (minimum, maximum) in RETENTION_LIMITS.items():
        value = getattr(data, field_name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise HTTPException(
                status_code=422,
                detail=f"{field_name} must be an integer",
            )
        if not minimum <= value <= maximum:
            raise HTTPException(
                status_code=422,
                detail=f"{field_name} must be between {minimum} and {maximum}",
            )
    if not isinstance(data.allow_model_training, bool):
        raise HTTPException(
            status_code=422,
            detail="allow_model_training must be a boolean",
        )


def _cleanup_media(
    db: Session,
    row: MediaAsset,
    root: Path,
    actor: Actor,
    cleaned_at: datetime,
) -> CleanupItem:
    file_result, detail = _delete_storage_file(root, row.storage_key)
    database_status = "deleted" if file_result in {"deleted", "missing"} else "cleanup_failed"
    audit = _cleanup_audit(
        actor,
        cleaned_at,
        file_result,
        detail,
        database_status=database_status,
    )
    metadata = row.metadata_json or {}
    events = _append_audit_event(metadata.get("retention_cleanup_events"), audit)
    row.metadata_json = {
        **metadata,
        "retention_cleanup": audit,
        "retention_cleanup_events": events,
    }
    row.status = database_status
    if database_status == "deleted":
        row.deleted_at = cleaned_at
    db.add(row)
    return CleanupItem(
        record_type="media_asset",
        record_id=row.id,
        storage_key=row.storage_key,
        database_status=database_status,
        file_result=file_result,
        detail=detail,
    )


def _cleanup_export_package(
    db: Session,
    row: PlatformExportPackage,
    root: Path,
    actor: Actor,
    cleaned_at: datetime,
) -> CleanupItem:
    file_result, detail = _delete_storage_file(root, row.storage_key)
    database_status = "deleted" if file_result in {"deleted", "missing"} else "cleanup_failed"
    manifest = row.manifest or {}
    audit = _cleanup_audit(
        actor,
        cleaned_at,
        file_result,
        detail,
        database_status=database_status,
    )
    events = _append_audit_event(manifest.get("retention_cleanup_events"), audit)
    row.manifest = {
        **manifest,
        "retention_cleanup": audit,
        "retention_cleanup_events": events,
    }
    if database_status == "deleted":
        row.expires_at = cleaned_at
    db.add(row)
    return CleanupItem(
        record_type="platform_export_package",
        record_id=row.id,
        storage_key=row.storage_key,
        database_status=database_status,
        file_result=file_result,
        detail=detail,
    )


def _delete_storage_file(root: Path, storage_key: str) -> tuple[str, str]:
    try:
        path = _resolve_storage_path(root, storage_key)
    except ValueError as exc:
        return "blocked", str(exc)
    if not path.exists():
        return "missing", ""
    if not path.is_file():
        return "blocked", "Storage target is not a regular file"
    try:
        path.unlink()
    except OSError as exc:
        return "error", f"{type(exc).__name__}: {exc}"
    return "deleted", ""


def _storage_root(
    configured: str | Path | None,
    *,
    env_name: str,
    default: Path,
) -> Path:
    value = configured or os.getenv(env_name) or default
    return Path(value).expanduser().resolve()


def _resolve_storage_path(root: Path, storage_key: str) -> Path:
    path = (root / Path(storage_key)).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("Storage path is outside the configured root") from exc
    return path


def _is_expired(
    expires_at: datetime | None,
    created_at: datetime,
    retention_cutoff: datetime,
    now: datetime,
) -> bool:
    if expires_at is not None:
        return _aware(expires_at) <= now
    return _aware(created_at) <= retention_cutoff


def _export_cleanup_recorded(row: PlatformExportPackage) -> bool:
    cleanup = (row.manifest or {}).get("retention_cleanup")
    return isinstance(cleanup, dict) and cleanup.get("database_status") == "deleted"


def _cleanup_audit(
    actor: Actor,
    cleaned_at: datetime,
    file_result: str,
    detail: str,
    *,
    database_status: str | None = None,
) -> dict[str, Any]:
    audit = {
        "cleaned_at": cleaned_at.isoformat(),
        "cleaned_by": actor.user_id,
        "file_result": file_result,
        "detail": detail,
    }
    if database_status is not None:
        audit["database_status"] = database_status
    return audit


def _append_audit_event(existing: Any, event: dict[str, Any]) -> list[dict[str, Any]]:
    events = list(existing) if isinstance(existing, list) else []
    return [*events, event]


def _tenant_rows(db: Session, model: Any, organization_id: str) -> list[Any]:
    return list(
        db.scalars(
            select(model)
            .where(model.organization_id == organization_id)
            .order_by(model.created_at, model.id)
        ).all()
    )


def _provider_record(row: ProviderConnection) -> dict[str, Any]:
    payload = _record(row)
    payload.pop("encrypted_api_key", None)
    payload["secret_configured"] = bool(row.encrypted_api_key)
    return payload


def _record(row: Any) -> dict[str, Any]:
    return {column.name: _json_value(getattr(row, column.name)) for column in row.__table__.columns}


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return _aware(value).isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = [
    "CleanupItem",
    "CleanupReport",
    "DataPolicyUpdate",
    "RETENTION_LIMITS",
    "cleanup_expired_storage",
    "export_organization_data",
    "export_organization_data_json",
    "get_data_policy",
    "get_system_health",
    "require_governance_admin",
    "update_data_policy",
]
