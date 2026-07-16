from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Brand,
    ContentProject,
    ContentType,
    ContentVersion,
    Organization,
    PlatformExportPackage,
    Product,
    Publication,
    PublicationTask,
    ReviewStatus,
    Role,
    User,
)
from app.publication_workflow import (
    confirm_manual_publication,
    create_publication_task,
    get_export_package,
    get_publication_task,
    list_publication_task_events,
    locate_export_package_download,
    transition_publication_task,
)
from app.schemas import Actor


def _export_payload() -> dict[str, Any]:
    return {
        "title": "Seasonal tomato harvest",
        "caption": "Fresh tomatoes picked this morning and ready for local delivery.",
        "hashtags": ["seasonal", "tomato"],
        "cover_copy": "Picked today",
        "subtitles": [
            {"start_ms": 0, "end_ms": 1200, "text": "Fresh from the field"},
            {"start_ms": 1200, "end_ms": 2500, "text": "Ready for local delivery"},
        ],
        "shots": [
            {
                "order": 1,
                "timing": "0-3s",
                "visual": "Farmer picks a ripe tomato",
                "voiceover": "Picked this morning",
                "filming_tip": "Use natural light",
            }
        ],
        "checklist": ["Confirm the final price before upload"],
        "locale": "en",
    }


def _create_workspace(
    db: Session,
    *,
    slug: str,
    approved: bool = True,
) -> tuple[Actor, ContentProject, ContentVersion]:
    user = User(
        email=f"owner@{slug}.example",
        display_name=f"{slug} Owner",
        password_hash="test-password-hash",
    )
    organization = Organization(name=slug.title(), slug=slug)
    db.add_all([user, organization])
    db.flush()

    brand = Brand(
        organization_id=organization.id,
        name=f"{slug} Farm",
        status=ReviewStatus.approved,
    )
    db.add(brand)
    db.flush()
    product = Product(
        organization_id=organization.id,
        brand_id=brand.id,
        name="Tomato",
        status=ReviewStatus.approved,
    )
    db.add(product)
    db.flush()
    project = ContentProject(
        organization_id=organization.id,
        brand_id=brand.id,
        product_id=product.id,
        title="Tomato launch",
        content_type=ContentType.short_video_30s,
        platform="douyin",
        created_by=user.id,
    )
    db.add(project)
    db.flush()
    version = ContentVersion(
        organization_id=organization.id,
        project_id=project.id,
        version_number=1,
        content={"format": "short_video_30s"},
        status=ReviewStatus.approved if approved else ReviewStatus.draft,
        created_by=user.id,
        reviewed_by=user.id if approved else None,
    )
    db.add(version)
    db.commit()
    return (
        Actor(
            user_id=user.id,
            organization_id=organization.id,
            role=Role.owner,
        ),
        project,
        version,
    )


def _create_task(
    db: Session,
    actor: Actor,
    project: ContentProject,
    version: ContentVersion,
    storage_root: Path,
    *,
    execution_mode: str = "export_only",
):
    return create_publication_task(
        db,
        actor,
        project_id=project.id,
        content_version_id=version.id,
        platform="douyin",
        execution_mode=execution_mode,
        export_payload=_export_payload(),
        storage_root=storage_root,
    )


def _assert_http_error(expected_status: int, call) -> HTTPException:
    with pytest.raises(HTTPException) as raised:
        call()
    assert raised.value.status_code == expected_status
    return raised.value


def test_create_task_persists_deterministic_private_export_and_events(
    db: Session,
    tmp_path: Path,
):
    actor, project, version = _create_workspace(db, slug="green")

    first = _create_task(db, actor, project, version, tmp_path)
    second = _create_task(db, actor, project, version, tmp_path)

    assert first.task.status == "package_ready"
    assert first.task.execution_mode == "export_only"
    assert first.package.organization_id == actor.organization_id
    assert first.package.content_sha256 == second.package.content_sha256
    assert first.package.archive_sha256 == second.package.archive_sha256
    assert first.package.archive_size_bytes == second.package.archive_size_bytes

    download = locate_export_package_download(
        db,
        actor,
        first.package.id,
        storage_root=tmp_path,
    )
    assert download.path.is_file()
    assert download.path.is_relative_to(tmp_path.resolve())
    assert download.size_bytes == first.package.archive_size_bytes
    assert download.sha256 == first.package.archive_sha256

    events = list_publication_task_events(db, actor, first.task.id)
    assert [(event.from_status, event.to_status) for event in events] == [
        ("", "draft"),
        ("draft", "package_ready"),
    ]
    assert events[-1].details["package_id"] == first.package.id


def test_authorized_api_is_explicitly_unavailable_and_creates_nothing(
    db: Session,
    tmp_path: Path,
):
    actor, project, version = _create_workspace(db, slug="no-api")

    error = _assert_http_error(
        409,
        lambda: create_publication_task(
            db,
            actor,
            project_id=project.id,
            content_version_id=version.id,
            platform="douyin",
            execution_mode="authorized_api",
            export_payload=_export_payload(),
            storage_root=tmp_path,
        ),
    )

    assert "unavailable" in str(error.detail)
    assert db.scalar(select(func.count()).select_from(PublicationTask)) == 0
    assert db.scalar(select(func.count()).select_from(PlatformExportPackage)) == 0


def test_state_machine_allows_review_flow_and_rejects_illegal_transitions(
    db: Session,
    tmp_path: Path,
):
    actor, project, version = _create_workspace(db, slug="states")
    bundle = _create_task(db, actor, project, version, tmp_path)

    awaiting = transition_publication_task(
        db,
        actor,
        bundle.task.id,
        to_status="awaiting_manual_confirmation",
    )
    assert awaiting.status == "awaiting_manual_confirmation"

    returned = transition_publication_task(
        db,
        actor,
        bundle.task.id,
        to_status="package_ready",
        details={"reason": "caption needs revision"},
    )
    assert returned.status == "package_ready"

    _assert_http_error(
        409,
        lambda: transition_publication_task(
            db,
            actor,
            bundle.task.id,
            to_status="published",
        ),
    )
    _assert_http_error(
        409,
        lambda: transition_publication_task(
            db,
            actor,
            bundle.task.id,
            to_status="draft",
        ),
    )

    cancelled = transition_publication_task(
        db,
        actor,
        bundle.task.id,
        to_status="cancelled",
    )
    assert cancelled.status == "cancelled"
    _assert_http_error(
        409,
        lambda: transition_publication_task(
            db,
            actor,
            bundle.task.id,
            to_status="package_ready",
        ),
    )


def test_manual_confirmation_requires_locator_and_then_creates_publication(
    db: Session,
    tmp_path: Path,
):
    actor, project, version = _create_workspace(db, slug="publish")
    bundle = _create_task(db, actor, project, version, tmp_path)

    assert db.scalar(select(func.count()).select_from(Publication)) == 0
    _assert_http_error(
        409,
        lambda: confirm_manual_publication(
            db,
            actor,
            bundle.task.id,
            external_content_id="douyin-123",
        ),
    )
    transition_publication_task(
        db,
        actor,
        bundle.task.id,
        to_status="awaiting_manual_confirmation",
    )
    _assert_http_error(
        422,
        lambda: confirm_manual_publication(db, actor, bundle.task.id),
    )
    assert db.scalar(select(func.count()).select_from(Publication)) == 0

    published_at = datetime(2026, 7, 16, 9, 30, tzinfo=UTC)
    publication = confirm_manual_publication(
        db,
        actor,
        bundle.task.id,
        external_url="https://www.douyin.com/video/123",
        external_content_id="douyin-123",
        published_at=published_at,
        note="Uploaded and checked by the operator",
    )

    assert publication.organization_id == actor.organization_id
    assert publication.project_id == project.id
    assert publication.content_version_id == version.id
    assert publication.external_content_id == "douyin-123"
    assert db.scalar(select(func.count()).select_from(Publication)) == 1
    task = get_publication_task(db, actor, bundle.task.id)
    assert task.status == "published"
    assert task.external_url == "https://www.douyin.com/video/123"
    assert list_publication_task_events(db, actor, task.id)[-1].details["manual_confirmation"]


def test_mock_task_can_never_create_real_publication(
    db: Session,
    tmp_path: Path,
):
    actor, project, version = _create_workspace(db, slug="mock")
    bundle = _create_task(
        db,
        actor,
        project,
        version,
        tmp_path,
        execution_mode="mock",
    )
    transition_publication_task(
        db,
        actor,
        bundle.task.id,
        to_status="awaiting_manual_confirmation",
    )

    _assert_http_error(
        409,
        lambda: confirm_manual_publication(
            db,
            actor,
            bundle.task.id,
            external_content_id="should-not-exist",
        ),
    )
    assert db.scalar(select(func.count()).select_from(Publication)) == 0


def test_tenant_isolation_hides_tasks_packages_and_downloads(
    db: Session,
    tmp_path: Path,
):
    owner, project, version = _create_workspace(db, slug="owner-tenant")
    outsider, _, _ = _create_workspace(db, slug="other-tenant")
    bundle = _create_task(db, owner, project, version, tmp_path)

    _assert_http_error(
        404,
        lambda: get_publication_task(db, outsider, bundle.task.id),
    )
    _assert_http_error(
        404,
        lambda: get_export_package(db, outsider, bundle.package.id),
    )
    _assert_http_error(
        404,
        lambda: locate_export_package_download(
            db,
            outsider,
            bundle.package.id,
            storage_root=tmp_path,
        ),
    )


def test_download_rejects_tampered_archive_and_unsafe_storage_key(
    db: Session,
    tmp_path: Path,
):
    actor, project, version = _create_workspace(db, slug="integrity")
    bundle = _create_task(db, actor, project, version, tmp_path)
    download = locate_export_package_download(
        db,
        actor,
        bundle.package.id,
        storage_root=tmp_path,
    )
    download.path.write_bytes(b"tampered")

    _assert_http_error(
        409,
        lambda: locate_export_package_download(
            db,
            actor,
            bundle.package.id,
            storage_root=tmp_path,
        ),
    )

    bundle.package.storage_key = "../outside.zip"
    db.commit()
    _assert_http_error(
        409,
        lambda: locate_export_package_download(
            db,
            actor,
            bundle.package.id,
            storage_root=tmp_path,
        ),
    )


def test_unapproved_content_cannot_be_recorded_as_published(
    db: Session,
    tmp_path: Path,
):
    actor, project, version = _create_workspace(db, slug="draft-content", approved=False)
    bundle = _create_task(db, actor, project, version, tmp_path)
    transition_publication_task(
        db,
        actor,
        bundle.task.id,
        to_status="awaiting_manual_confirmation",
    )

    _assert_http_error(
        409,
        lambda: confirm_manual_publication(
            db,
            actor,
            bundle.task.id,
            external_content_id="draft-must-not-publish",
        ),
    )
    assert db.scalar(select(func.count()).select_from(Publication)) == 0
