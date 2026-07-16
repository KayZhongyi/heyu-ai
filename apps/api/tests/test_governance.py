from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.governance import (
    DataPolicyUpdate,
    cleanup_expired_storage,
    export_organization_data,
    export_organization_data_json,
    get_data_policy,
    get_system_health,
    update_data_policy,
)
from app.models import (
    BackgroundTask,
    MediaAsset,
    Organization,
    PlatformExportPackage,
    ProviderConnection,
    PublicationTask,
    Role,
    User,
    utc_now,
)
from app.schemas import Actor


def _actor(db: Session, slug: str, role: Role = Role.owner) -> Actor:
    user = User(
        email=f"{slug}@example.com",
        display_name=slug,
        password_hash="test",
    )
    organization = Organization(name=slug, slug=slug)
    db.add_all([user, organization])
    db.commit()
    return Actor(
        user_id=user.id,
        organization_id=organization.id,
        role=role,
    )


def _publication_task(db: Session, actor: Actor) -> PublicationTask:
    task = PublicationTask(
        organization_id=actor.organization_id,
        project_id="project-for-governance",
        content_version_id="version-for-governance",
        platform="douyin",
        execution_mode="export_only",
        created_by=actor.user_id,
    )
    db.add(task)
    db.flush()
    return task


def test_data_policy_defaults_update_validation_and_permissions(db: Session):
    owner = _actor(db, "policy-owner")
    policy = get_data_policy(db, owner)
    assert policy.media_retention_days == 90
    assert policy.export_retention_days == 30
    assert policy.updated_by == owner.user_id

    updated = update_data_policy(
        db,
        owner,
        DataPolicyUpdate(
            media_retention_days=120,
            export_retention_days=45,
            generation_log_retention_days=730,
            allow_model_training=True,
        ),
    )
    assert updated.media_retention_days == 120
    assert updated.allow_model_training is True

    admin = Actor(
        user_id=owner.user_id,
        organization_id=owner.organization_id,
        role=Role.admin,
    )
    assert get_data_policy(db, admin).organization_id == owner.organization_id

    with pytest.raises(HTTPException) as invalid:
        update_data_policy(
            db,
            owner,
            DataPolicyUpdate(export_retention_days=0),
        )
    assert invalid.value.status_code == 422

    viewer = Actor(
        user_id=owner.user_id,
        organization_id=owner.organization_id,
        role=Role.viewer,
    )
    with pytest.raises(HTTPException) as forbidden:
        get_data_policy(db, viewer)
    assert forbidden.value.status_code == 403


def test_cleanup_is_tenant_scoped_safe_and_auditable(db: Session, tmp_path: Path):
    now = datetime(2026, 7, 16, 8, tzinfo=UTC)
    owner = _actor(db, "cleanup-owner")
    outsider = _actor(db, "cleanup-outsider")
    update_data_policy(
        db,
        owner,
        DataPolicyUpdate(media_retention_days=30, export_retention_days=10),
    )
    media_root = tmp_path / "media"
    export_root = tmp_path / "exports"

    expired_media_path = media_root / owner.organization_id / "old.mp4"
    expired_media_path.parent.mkdir(parents=True)
    expired_media_path.write_bytes(b"old video")
    expired_media = MediaAsset(
        organization_id=owner.organization_id,
        purpose="video_analysis",
        original_filename="old.mp4",
        media_type="video/mp4",
        size_bytes=9,
        sha256="a" * 64,
        storage_key=f"{owner.organization_id}/old.mp4",
        expires_at=now - timedelta(days=1),
        created_by=owner.user_id,
    )
    retained_media_path = media_root / owner.organization_id / "new.mp4"
    retained_media_path.write_bytes(b"new video")
    retained_media = MediaAsset(
        organization_id=owner.organization_id,
        purpose="video_analysis",
        original_filename="new.mp4",
        media_type="video/mp4",
        size_bytes=9,
        sha256="b" * 64,
        storage_key=f"{owner.organization_id}/new.mp4",
        expires_at=now + timedelta(days=1),
        created_by=owner.user_id,
    )
    outsider_path = media_root / outsider.organization_id / "old.mp4"
    outsider_path.parent.mkdir(parents=True)
    outsider_path.write_bytes(b"outsider")
    outsider_media = MediaAsset(
        organization_id=outsider.organization_id,
        purpose="video_analysis",
        original_filename="old.mp4",
        media_type="video/mp4",
        size_bytes=8,
        sha256="c" * 64,
        storage_key=f"{outsider.organization_id}/old.mp4",
        expires_at=now - timedelta(days=1),
        created_by=outsider.user_id,
    )
    blocked_media = MediaAsset(
        organization_id=owner.organization_id,
        purpose="video_analysis",
        original_filename="escape.mp4",
        media_type="video/mp4",
        size_bytes=6,
        sha256="d" * 64,
        storage_key="../escape.mp4",
        expires_at=now - timedelta(days=1),
        created_by=owner.user_id,
    )
    policy_expired_media = MediaAsset(
        organization_id=owner.organization_id,
        purpose="video_analysis",
        original_filename="missing.mp4",
        media_type="video/mp4",
        size_bytes=6,
        sha256="e" * 64,
        storage_key=f"{owner.organization_id}/missing.mp4",
        created_at=now - timedelta(days=31),
        created_by=owner.user_id,
    )
    db.add_all(
        [
            expired_media,
            retained_media,
            outsider_media,
            blocked_media,
            policy_expired_media,
        ]
    )
    db.commit()

    report = cleanup_expired_storage(
        db,
        owner,
        media_storage_root=media_root,
        export_storage_root=export_root,
        now=now,
    )

    db.refresh(expired_media)
    db.refresh(retained_media)
    db.refresh(outsider_media)
    db.refresh(blocked_media)
    assert not expired_media_path.exists()
    assert expired_media.status == "deleted"
    assert expired_media.deleted_at is not None
    assert expired_media.deleted_at.replace(tzinfo=UTC) == now
    assert expired_media.metadata_json["retention_cleanup"]["file_result"] == "deleted"
    assert retained_media_path.exists()
    assert retained_media.deleted_at is None
    assert outsider_path.exists()
    assert outsider_media.deleted_at is None
    assert blocked_media.status == "cleanup_failed"
    assert blocked_media.deleted_at is None
    assert blocked_media.metadata_json["retention_cleanup"]["file_result"] == "blocked"
    db.refresh(policy_expired_media)
    assert policy_expired_media.status == "deleted"
    assert policy_expired_media.metadata_json["retention_cleanup"]["file_result"] == "missing"
    assert report.deleted_files == 1
    assert report.failed_records == 1


def test_export_package_cleanup_marks_manifest_and_is_idempotent(
    db: Session,
    tmp_path: Path,
):
    now = datetime(2026, 7, 16, 8, tzinfo=UTC)
    owner = _actor(db, "package-cleanup")
    task = _publication_task(db, owner)
    storage_key = f"{owner.organization_id}/{task.id}/package.zip"
    archive = tmp_path / storage_key
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"zip")
    package = PlatformExportPackage(
        organization_id=owner.organization_id,
        publication_task_id=task.id,
        platform="douyin",
        execution_mode="export_only",
        content_sha256="e" * 64,
        archive_sha256="f" * 64,
        archive_size_bytes=3,
        storage_key=storage_key,
        manifest={"schema": "test"},
        expires_at=now - timedelta(minutes=1),
        created_by=owner.user_id,
    )
    db.add(package)
    db.commit()

    first = cleanup_expired_storage(
        db,
        owner,
        media_storage_root=tmp_path / "media",
        export_storage_root=tmp_path,
        now=now,
    )
    db.refresh(package)
    assert not archive.exists()
    assert first.export_packages[0].database_status == "deleted"
    assert package.manifest["retention_cleanup"]["database_status"] == "deleted"
    assert package.manifest["retention_cleanup"]["file_result"] == "deleted"

    second = cleanup_expired_storage(
        db,
        owner,
        media_storage_root=tmp_path / "media",
        export_storage_root=tmp_path,
        now=now,
    )
    assert second.export_packages == ()


def test_organization_export_excludes_provider_secret_and_other_tenants(db: Session):
    owner = _actor(db, "export-owner")
    outsider = _actor(db, "export-outsider")
    provider = ProviderConnection(
        organization_id=owner.organization_id,
        name="Primary",
        base_url="https://api.example.com/v1",
        chat_model="chat-model",
        encrypted_api_key="env:OWNER_PROVIDER_KEY",
        is_primary=True,
        created_by=owner.user_id,
    )
    outsider_provider = ProviderConnection(
        organization_id=outsider.organization_id,
        name="Outsider",
        base_url="https://api.example.com/v1",
        chat_model="other-model",
        encrypted_api_key="env:OUTSIDER_PROVIDER_KEY",
        created_by=outsider.user_id,
    )
    db.add_all([provider, outsider_provider])
    db.commit()

    payload = export_organization_data(db, owner)
    encoded = export_organization_data_json(db, owner)

    assert payload["organization"]["id"] == owner.organization_id
    assert [item["name"] for item in payload["provider_connections"]] == ["Primary"]
    assert "encrypted_api_key" not in payload["provider_connections"][0]
    assert payload["provider_connections"][0]["secret_configured"] is True
    assert b"OWNER_PROVIDER_KEY" not in encoded
    assert b"OUTSIDER_PROVIDER_KEY" not in encoded
    assert json.loads(encoded)["schema_version"] == "organization-governance-export-v1"


def test_health_summary_reports_persisted_facts_only(db: Session):
    owner = _actor(db, "health-owner")
    provider = ProviderConnection(
        organization_id=owner.organization_id,
        name="Untested provider",
        base_url="https://api.example.com/v1",
        chat_model="chat-model",
        encrypted_api_key="env:HEALTH_PROVIDER_KEY",
        enabled=True,
        is_primary=True,
        last_test_status="untested",
        created_by=owner.user_id,
    )
    pending = BackgroundTask(
        organization_id=owner.organization_id,
        task_type="index",
        idempotency_key="pending-task",
        status="pending",
        created_by=owner.user_id,
    )
    overdue = BackgroundTask(
        organization_id=owner.organization_id,
        task_type="video",
        idempotency_key="overdue-task",
        status="running",
        lease_expires_at=utc_now() - timedelta(minutes=5),
        created_by=owner.user_id,
    )
    db.add_all([provider, pending, overdue])
    db.commit()

    summary = get_system_health(db, owner)

    assert summary["database"]["status"] == "ok"
    assert summary["providers"] == {
        "total": 1,
        "enabled": 1,
        "primary": 1,
        "fallback": 0,
        "last_test_status_counts": {"untested": 1},
        "never_tested": 1,
    }
    assert summary["background_tasks"]["status_counts"] == {
        "pending": 1,
        "running": 1,
    }
    assert summary["background_tasks"]["overdue_running_leases"] == 1
