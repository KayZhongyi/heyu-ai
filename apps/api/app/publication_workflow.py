"""Manual-first publication collaboration workflow.

The workflow creates deterministic platform export packages, stores them in a
tenant-scoped private directory, and records explicit task transitions. It does
not call external publishing APIs. A ``Publication`` is recorded only after a
person confirms the upload and supplies an external URL or content identifier.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    ContentProject,
    ContentVersion,
    MarketingPlan,
    MarketingPlanVersion,
    Publication,
    PublicationTask,
    PublicationTaskEvent,
    new_id,
    utc_now,
)
from app.models import (
    PlatformExportPackage as PlatformExportPackageRow,
)
from app.platform_exports import (
    ExportCapabilityUnavailable,
    PlatformExportError,
    PlatformExportPackage,
    PlatformValidationError,
    generate_platform_export,
)
from app.publication_locators import (
    assert_publication_locator_available,
    locator_conflict,
)
from app.schemas import Actor, PublicationCreate

ExecutionMode = Literal["export_only", "mock"]
TaskStatus = Literal[
    "draft",
    "package_ready",
    "awaiting_manual_confirmation",
    "published",
    "cancelled",
]

DEFAULT_STORAGE_ENV = "PLATFORM_EXPORT_STORAGE_DIR"
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"package_ready", "cancelled"}),
    "package_ready": frozenset({"awaiting_manual_confirmation", "cancelled"}),
    "awaiting_manual_confirmation": frozenset({"package_ready", "cancelled"}),
    "published": frozenset(),
    "cancelled": frozenset(),
}


@dataclass(frozen=True, slots=True)
class PublicationTaskBundle:
    task: PublicationTask
    package: PlatformExportPackageRow


@dataclass(frozen=True, slots=True)
class VerifiedExportDownload:
    package: PlatformExportPackageRow
    path: Path
    size_bytes: int
    sha256: str


def create_publication_task(
    db: Session,
    actor: Actor,
    *,
    project_id: str,
    content_version_id: str,
    platform: str,
    execution_mode: str,
    export_payload: Mapping[str, Any],
    storage_root: str | Path | None = None,
    scheduled_for: datetime | None = None,
    note: str = "",
) -> PublicationTaskBundle:
    """Create a task and persist its deterministic ZIP export package."""

    _validate_execution_mode(execution_mode)

    project, version = _get_project_and_version(
        db,
        organization_id=actor.organization_id,
        project_id=project_id,
        content_version_id=content_version_id,
    )
    payload = dict(export_payload)
    payload["platform"] = platform
    payload["mode"] = execution_mode
    try:
        generated = generate_platform_export(payload)
        archive = generated.zip_bytes()
    except ExportCapabilityUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (PlatformValidationError, PlatformExportError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return _persist_publication_task(
        db,
        actor,
        generated=generated,
        archive=archive,
        project_id=project.id,
        content_version_id=version.id,
        storage_root=storage_root,
        scheduled_for=scheduled_for,
        note=note,
    )


def create_marketing_plan_publication_task(
    db: Session,
    actor: Actor,
    *,
    marketing_plan_id: str,
    marketing_plan_version_id: str | None,
    route_id: str,
    calendar_day: int,
    execution_mode: str,
    storage_root: str | Path | None = None,
    scheduled_for: datetime | None = None,
    note: str = "",
) -> PublicationTaskBundle:
    """Create a manual publication task from one saved marketing-plan route."""

    _validate_execution_mode(execution_mode)
    if not 1 <= calendar_day <= 7:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="calendar_day must be between 1 and 7",
        )

    from app.marketing_exports import export_saved_marketing_plan
    from app.services import get_marketing_plan

    plan = get_marketing_plan(db, actor, marketing_plan_id)
    selected_version_id = marketing_plan_version_id or plan.current_version.id
    try:
        exported = export_saved_marketing_plan(
            plan,
            route_id,
            version_id=selected_version_id,
            execution_mode=execution_mode,  # type: ignore[arg-type]
        )
    except ExportCapabilityUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (PlatformValidationError, PlatformExportError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return _persist_publication_task(
        db,
        actor,
        generated=exported.package,
        archive=exported.package.zip_bytes(),
        marketing_plan_id=plan.id,
        marketing_plan_version_id=selected_version_id,
        route_id=route_id,
        calendar_day=calendar_day,
        storage_root=storage_root,
        scheduled_for=scheduled_for,
        note=note,
    )


def _persist_publication_task(
    db: Session,
    actor: Actor,
    *,
    generated: PlatformExportPackage,
    archive: bytes,
    project_id: str | None = None,
    content_version_id: str | None = None,
    marketing_plan_id: str | None = None,
    marketing_plan_version_id: str | None = None,
    route_id: str = "",
    calendar_day: int | None = None,
    storage_root: str | Path | None = None,
    scheduled_for: datetime | None = None,
    note: str = "",
) -> PublicationTaskBundle:
    _validate_source_pair(
        project_id=project_id,
        content_version_id=content_version_id,
        marketing_plan_id=marketing_plan_id,
        marketing_plan_version_id=marketing_plan_version_id,
    )
    task_id = new_id()
    package_id = new_id()
    storage_key = _storage_key(actor.organization_id, task_id, package_id)
    archive_path = _resolve_storage_path(storage_root, storage_key)
    archive_sha256 = hashlib.sha256(archive).hexdigest()
    draft_event_at = utc_now()

    _write_private_archive(archive_path, archive)
    task = PublicationTask(
        id=task_id,
        organization_id=actor.organization_id,
        project_id=project_id,
        content_version_id=content_version_id,
        marketing_plan_id=marketing_plan_id,
        marketing_plan_version_id=marketing_plan_version_id,
        route_id=route_id.strip(),
        calendar_day=calendar_day,
        platform=generated.platform,
        execution_mode=generated.mode,
        status="package_ready",
        scheduled_for=scheduled_for,
        note=note.strip(),
        created_by=actor.user_id,
    )
    package = PlatformExportPackageRow(
        id=package_id,
        organization_id=actor.organization_id,
        publication_task_id=task.id,
        platform=generated.platform,
        execution_mode=generated.mode,
        content_sha256=generated.content_hash,
        archive_sha256=archive_sha256,
        archive_size_bytes=len(archive),
        storage_key=storage_key,
        manifest=dict(generated.manifest),
        created_by=actor.user_id,
    )
    source_details = {
        "project_id": project_id,
        "content_version_id": content_version_id,
        "marketing_plan_id": marketing_plan_id,
        "marketing_plan_version_id": marketing_plan_version_id,
        "route_id": route_id,
        "calendar_day": calendar_day,
    }
    db.add_all(
        [
            task,
            _event(
                actor,
                task,
                from_status="",
                to_status="draft",
                details={
                    "execution_mode": generated.mode,
                    **source_details,
                },
                created_at=draft_event_at,
            ),
            package,
            _event(
                actor,
                task,
                from_status="draft",
                to_status="package_ready",
                details={
                    "package_id": package.id,
                    "archive_sha256": archive_sha256,
                    "archive_size_bytes": len(archive),
                    **source_details,
                },
                created_at=draft_event_at + timedelta(microseconds=1),
            ),
        ]
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        archive_path.unlink(missing_ok=True)
        raise
    db.refresh(task)
    db.refresh(package)
    return PublicationTaskBundle(task=task, package=package)


def get_publication_task(
    db: Session,
    actor: Actor,
    task_id: str,
) -> PublicationTask:
    task = db.scalar(
        select(PublicationTask).where(
            PublicationTask.id == task_id,
            PublicationTask.organization_id == actor.organization_id,
        )
    )
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Publication task not found"
        )
    return task


def list_publication_tasks(
    db: Session,
    actor: Actor,
) -> list[PublicationTask]:
    return list(
        db.scalars(
            select(PublicationTask)
            .where(PublicationTask.organization_id == actor.organization_id)
            .order_by(PublicationTask.created_at.desc(), PublicationTask.id.desc())
        )
    )


def list_publication_task_events(
    db: Session,
    actor: Actor,
    task_id: str,
) -> list[PublicationTaskEvent]:
    task = get_publication_task(db, actor, task_id)
    return list(
        db.scalars(
            select(PublicationTaskEvent)
            .where(
                PublicationTaskEvent.publication_task_id == task.id,
                PublicationTaskEvent.organization_id == actor.organization_id,
            )
            .order_by(
                PublicationTaskEvent.created_at.asc(),
                PublicationTaskEvent.id.asc(),
            )
        )
    )


def transition_publication_task(
    db: Session,
    actor: Actor,
    task_id: str,
    *,
    to_status: str,
    details: Mapping[str, Any] | None = None,
) -> PublicationTask:
    """Apply a legal non-publication state transition.

    ``published`` is intentionally unavailable here; callers must use
    :func:`confirm_manual_publication`.
    """

    task = get_publication_task(db, actor, task_id)
    if to_status == "published":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Use manual publication confirmation to mark a task as published",
        )
    if task.execution_mode == "mock" and to_status == "awaiting_manual_confirmation":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Mock tasks are complete when the export package is ready and cannot "
                "enter manual publication confirmation"
            ),
        )
    _validate_transition(task.status, to_status)
    previous = task.status
    task.status = to_status
    task.updated_at = utc_now()
    db.add(
        _event(
            actor,
            task,
            from_status=previous,
            to_status=to_status,
            details=dict(details or {}),
        )
    )
    db.commit()
    db.refresh(task)
    return task


def confirm_manual_publication(
    db: Session,
    actor: Actor,
    task_id: str,
    *,
    external_url: str = "",
    external_content_id: str = "",
    published_at: datetime | None = None,
    note: str = "",
) -> Publication:
    """Record a real publication after explicit human confirmation."""

    task = get_publication_task(db, actor, task_id)
    if task.execution_mode != "export_only":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Mock tasks cannot be confirmed as real publications",
        )
    if task.status != "awaiting_manual_confirmation":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Task must be awaiting_manual_confirmation before a publication can be recorded"
            ),
        )

    normalized_url = external_url.strip()
    normalized_content_id = external_content_id.strip()
    if not normalized_url and not normalized_content_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="An external URL or external content ID is required",
        )
    if len(normalized_url) > 2048 or len(normalized_content_id) > 255:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="External publication locator is too long",
        )
    if normalized_url:
        parsed = urlsplit(normalized_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="External URL must be an absolute HTTP or HTTPS URL",
            )
    assert_publication_locator_available(
        db,
        organization_id=actor.organization_id,
        platform=task.platform,
        external_url=normalized_url,
        external_content_id=normalized_content_id,
    )

    published_timestamp = published_at or utc_now()
    if task.project_id is not None and task.content_version_id is not None:
        # Reuse the legacy content system's canonical approval policy.
        from app.services import create_publication

        publication = create_publication(
            db,
            actor,
            PublicationCreate(
                project_id=task.project_id,
                content_version_id=task.content_version_id,
                platform=task.platform,
                external_url=normalized_url,
                external_content_id=normalized_content_id,
                published_at=published_timestamp,
                note=note.strip(),
            ),
        )
    elif task.marketing_plan_id is not None and task.marketing_plan_version_id is not None:
        plan, version = _get_marketing_plan_and_version(
            db,
            organization_id=actor.organization_id,
            marketing_plan_id=task.marketing_plan_id,
            marketing_plan_version_id=task.marketing_plan_version_id,
        )
        publication = Publication(
            organization_id=actor.organization_id,
            project_id=None,
            content_version_id=None,
            marketing_plan_id=plan.id,
            marketing_plan_version_id=version.id,
            route_id=task.route_id,
            calendar_day=task.calendar_day,
            platform=task.platform,
            external_url=normalized_url,
            external_content_id=normalized_content_id,
            published_at=published_timestamp,
            note=note.strip(),
            created_by=actor.user_id,
        )
        db.add(publication)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise locator_conflict() from exc
        from app.services import audit

        audit(
            db,
            actor,
            "publication.created",
            "publication",
            publication.id,
            {
                "marketing_plan_id": plan.id,
                "marketing_plan_version_id": version.id,
                "route_id": task.route_id,
                "calendar_day": task.calendar_day,
                "platform": publication.platform,
                "external_content_id": publication.external_content_id,
            },
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Publication task has no valid content source",
        )
    previous = task.status
    task.status = "published"
    task.external_url = normalized_url
    task.external_content_id = normalized_content_id
    task.note = note.strip() or task.note
    task.updated_at = utc_now()
    db.add(
        _event(
            actor,
            task,
            from_status=previous,
            to_status="published",
            details={
                "publication_id": publication.id,
                "external_url": normalized_url,
                "external_content_id": normalized_content_id,
                "manual_confirmation": True,
            },
        )
    )
    db.commit()
    db.refresh(task)
    return publication


def get_export_package(
    db: Session,
    actor: Actor,
    package_id: str,
) -> PlatformExportPackageRow:
    package = db.scalar(
        select(PlatformExportPackageRow).where(
            PlatformExportPackageRow.id == package_id,
            PlatformExportPackageRow.organization_id == actor.organization_id,
        )
    )
    if package is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Export package not found"
        )
    return package


def get_latest_export_package(
    db: Session,
    actor: Actor,
    task_id: str,
) -> PlatformExportPackageRow:
    task = get_publication_task(db, actor, task_id)
    package = db.scalar(
        select(PlatformExportPackageRow)
        .where(
            PlatformExportPackageRow.publication_task_id == task.id,
            PlatformExportPackageRow.organization_id == actor.organization_id,
        )
        .order_by(
            PlatformExportPackageRow.created_at.desc(),
            PlatformExportPackageRow.id.desc(),
        )
    )
    if package is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Export package not found"
        )
    return package


def locate_export_package_download(
    db: Session,
    actor: Actor,
    package_id: str,
    *,
    storage_root: str | Path | None = None,
) -> VerifiedExportDownload:
    """Locate a tenant-owned package and verify size and SHA-256 before download."""

    package = get_export_package(db, actor, package_id)
    if package.expires_at is not None and _is_expired(package.expires_at):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Export package has expired")
    archive_path = _resolve_storage_path(storage_root, package.storage_key)
    if not archive_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Export archive not found"
        )

    digest = hashlib.sha256()
    size_bytes = 0
    with archive_path.open("rb") as archive_file:
        for chunk in iter(lambda: archive_file.read(1024 * 1024), b""):
            digest.update(chunk)
            size_bytes += len(chunk)
    actual_sha256 = digest.hexdigest()
    if size_bytes != package.archive_size_bytes or actual_sha256 != package.archive_sha256:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Export archive failed integrity verification",
        )
    return VerifiedExportDownload(
        package=package,
        path=archive_path,
        size_bytes=size_bytes,
        sha256=actual_sha256,
    )


def _get_project_and_version(
    db: Session,
    *,
    organization_id: str,
    project_id: str,
    content_version_id: str,
) -> tuple[ContentProject, ContentVersion]:
    project = db.scalar(
        select(ContentProject).where(
            ContentProject.id == project_id,
            ContentProject.organization_id == organization_id,
        )
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Content project not found"
        )
    version = db.scalar(
        select(ContentVersion).where(
            ContentVersion.id == content_version_id,
            ContentVersion.project_id == project.id,
            ContentVersion.organization_id == organization_id,
        )
    )
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Content version not found"
        )
    return project, version


def _get_marketing_plan_and_version(
    db: Session,
    *,
    organization_id: str,
    marketing_plan_id: str,
    marketing_plan_version_id: str,
) -> tuple[MarketingPlan, MarketingPlanVersion]:
    plan = db.scalar(
        select(MarketingPlan).where(
            MarketingPlan.id == marketing_plan_id,
            MarketingPlan.organization_id == organization_id,
        )
    )
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Marketing plan not found",
        )
    version = db.scalar(
        select(MarketingPlanVersion).where(
            MarketingPlanVersion.id == marketing_plan_version_id,
            MarketingPlanVersion.marketing_plan_id == plan.id,
            MarketingPlanVersion.organization_id == organization_id,
        )
    )
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Marketing plan version not found",
        )
    return plan, version


def _validate_execution_mode(execution_mode: str) -> None:
    if execution_mode == "authorized_api":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "authorized_api is unavailable; use export_only or mock and complete "
                "publication manually"
            ),
        )
    if execution_mode not in ("export_only", "mock"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsupported execution mode: {execution_mode}",
        )


def _validate_source_pair(
    *,
    project_id: str | None,
    content_version_id: str | None,
    marketing_plan_id: str | None,
    marketing_plan_version_id: str | None,
) -> None:
    has_content = project_id is not None or content_version_id is not None
    has_marketing = marketing_plan_id is not None or marketing_plan_version_id is not None
    if has_content == has_marketing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Choose exactly one publication source",
        )
    if has_content and (project_id is None or content_version_id is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Both project_id and content_version_id are required",
        )
    if has_marketing and (marketing_plan_id is None or marketing_plan_version_id is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Both marketing plan source identifiers are required",
        )


def _event(
    actor: Actor,
    task: PublicationTask,
    *,
    from_status: str,
    to_status: str,
    details: Mapping[str, Any],
    created_at: datetime | None = None,
) -> PublicationTaskEvent:
    return PublicationTaskEvent(
        organization_id=actor.organization_id,
        publication_task_id=task.id,
        from_status=from_status,
        to_status=to_status,
        details=dict(details),
        created_by=actor.user_id,
        created_at=created_at or utc_now(),
    )


def _validate_transition(from_status: str, to_status: str) -> None:
    allowed = _ALLOWED_TRANSITIONS.get(from_status)
    if allowed is None or to_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Illegal publication task transition: {from_status} -> {to_status}",
        )


def _storage_root(storage_root: str | Path | None) -> Path:
    configured = storage_root or os.getenv(DEFAULT_STORAGE_ENV)
    if configured is None:
        configured = Path.cwd() / "private" / "platform-exports"
    return Path(configured).expanduser().resolve()


def _storage_key(organization_id: str, task_id: str, package_id: str) -> str:
    return f"{organization_id}/{task_id}/{package_id}.zip"


def _resolve_storage_path(storage_root: str | Path | None, storage_key: str) -> Path:
    root = _storage_root(storage_root)
    candidate = (root / Path(storage_key)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invalid export package storage location",
        ) from exc
    return candidate


def _write_private_archive(path: Path, archive: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    temporary = path.with_suffix(path.suffix + f".{new_id()}.tmp")
    try:
        with temporary.open("xb") as archive_file:
            archive_file.write(archive)
            archive_file.flush()
            os.fsync(archive_file.fileno())
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _is_expired(expires_at: datetime) -> bool:
    now = utc_now()
    if expires_at.tzinfo is None:
        return expires_at <= now.replace(tzinfo=None)
    return expires_at <= now


__all__ = [
    "DEFAULT_STORAGE_ENV",
    "ExecutionMode",
    "PublicationTaskBundle",
    "TaskStatus",
    "VerifiedExportDownload",
    "confirm_manual_publication",
    "create_marketing_plan_publication_task",
    "create_publication_task",
    "get_export_package",
    "get_latest_export_package",
    "get_publication_task",
    "list_publication_tasks",
    "list_publication_task_events",
    "locate_export_package_download",
    "transition_publication_task",
]
