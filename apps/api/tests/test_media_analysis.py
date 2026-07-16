from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import media_analysis
from app.media_analysis import locate_media_asset, save_and_analyze_video
from app.models import (
    Brand,
    ContentProject,
    ContentType,
    ContentVersion,
    Organization,
    Product,
    Publication,
    ReviewStatus,
    Role,
    User,
    utc_now,
)
from app.schemas import Actor


def _workspace(db: Session, slug: str) -> tuple[Actor, Publication]:
    user = User(
        email=f"{slug}@example.com",
        display_name=slug,
        password_hash="test",
    )
    organization = Organization(name=slug, slug=slug)
    db.add_all([user, organization])
    db.flush()
    brand = Brand(
        organization_id=organization.id,
        name=f"{slug} farm",
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
        title="Tomato video",
        content_type=ContentType.short_video_30s,
        created_by=user.id,
    )
    db.add(project)
    db.flush()
    version = ContentVersion(
        organization_id=organization.id,
        project_id=project.id,
        version_number=1,
        content={"format": "short_video_script"},
        status=ReviewStatus.approved,
        created_by=user.id,
    )
    db.add(version)
    db.flush()
    publication = Publication(
        organization_id=organization.id,
        project_id=project.id,
        content_version_id=version.id,
        platform="douyin",
        external_content_id=f"{slug}-video",
        published_at=utc_now(),
        created_by=user.id,
    )
    db.add(publication)
    db.commit()
    return (
        Actor(
            user_id=user.id,
            organization_id=organization.id,
            role=Role.owner,
        ),
        publication,
    )


def test_video_upload_falls_back_to_manual_without_claiming_ai_analysis(
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    actor, publication = _workspace(db, "manual-video")
    monkeypatch.setattr(media_analysis, "_probe_video", lambda *args, **kwargs: {})

    result = save_and_analyze_video(
        db,
        actor,
        publication_id=publication.id,
        original_filename="tomato.mp4",
        media_type="video/mp4",
        content=b"not-a-real-video-but-valid-upload-bytes",
        manual_transcript="Today we picked the seasonal tomatoes.",
        storage_root=tmp_path,
    )

    assert result.asset.sha256
    assert result.task.status == "completed"
    assert result.diagnosis.analysis_mode == "manual"
    assert result.diagnosis.transcript_excerpt.startswith("Today we picked")
    assert result.diagnosis.analysis_metadata["limitations"] == [
        "No semantic scene understanding was performed.",
        "No automatic speech recognition was performed.",
        "The diagnosis does not predict views, likes or sales.",
    ]
    assert locate_media_asset(db, actor, result.asset.id, storage_root=tmp_path).is_file()


def test_local_probe_produces_partial_technical_analysis_only(
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    actor, publication = _workspace(db, "partial-video")
    monkeypatch.setattr(
        media_analysis,
        "_probe_video",
        lambda *args, **kwargs: {
            "duration_seconds": 28.4,
            "width": 1080,
            "height": 1920,
        },
    )

    result = save_and_analyze_video(
        db,
        actor,
        publication_id=publication.id,
        original_filename="vertical.mov",
        media_type="video/quicktime",
        content=b"video-content",
        storage_root=tmp_path,
    )

    assert result.diagnosis.analysis_mode == "partial"
    assert {finding["category"] for finding in result.diagnosis.findings} == {
        "duration",
        "frame",
    }
    assert "content-level findings still require human review" in result.diagnosis.summary


def test_same_publication_and_file_is_idempotent(
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    actor, publication = _workspace(db, "repeat-video")
    monkeypatch.setattr(media_analysis, "_probe_video", lambda *args, **kwargs: {})
    kwargs = {
        "publication_id": publication.id,
        "original_filename": "repeat.mp4",
        "media_type": "video/mp4",
        "content": b"same-video",
        "storage_root": tmp_path,
    }

    first = save_and_analyze_video(db, actor, **kwargs)
    second = save_and_analyze_video(db, actor, **kwargs)

    assert second.asset.id == first.asset.id
    assert second.task.id == first.task.id
    assert second.diagnosis.id == first.diagnosis.id


def test_media_download_is_tenant_isolated_and_integrity_checked(
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    owner, publication = _workspace(db, "video-owner")
    outsider, _ = _workspace(db, "video-outsider")
    monkeypatch.setattr(media_analysis, "_probe_video", lambda *args, **kwargs: {})
    result = save_and_analyze_video(
        db,
        owner,
        publication_id=publication.id,
        original_filename="private.webm",
        media_type="video/webm",
        content=b"private-video",
        storage_root=tmp_path,
    )

    with pytest.raises(HTTPException) as hidden:
        locate_media_asset(db, outsider, result.asset.id, storage_root=tmp_path)
    assert hidden.value.status_code == 404

    path = locate_media_asset(db, owner, result.asset.id, storage_root=tmp_path)
    path.write_bytes(b"tampered-video")
    with pytest.raises(HTTPException) as tampered:
        locate_media_asset(db, owner, result.asset.id, storage_root=tmp_path)
    assert tampered.value.status_code == 409


@pytest.mark.parametrize(
    ("filename", "media_type", "content", "expected_status"),
    [
        ("video.exe", "application/octet-stream", b"x", 415),
        ("video.mp4", "video/mp4", b"", 422),
    ],
)
def test_invalid_video_uploads_are_rejected(
    db: Session,
    tmp_path: Path,
    filename: str,
    media_type: str,
    content: bytes,
    expected_status: int,
):
    actor, publication = _workspace(db, f"invalid-{expected_status}")
    with pytest.raises(HTTPException) as raised:
        save_and_analyze_video(
            db,
            actor,
            publication_id=publication.id,
            original_filename=filename,
            media_type=media_type,
            content=content,
            storage_root=tmp_path,
        )
    assert raised.value.status_code == expected_status
