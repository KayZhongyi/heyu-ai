"""Private video upload and explicitly degraded analysis.

This module never claims semantic video understanding when no speech-to-text or
vision provider is configured. Local ``ffprobe`` metadata produces ``partial``
analysis; otherwise the workflow remains ``manual`` and preserves any
operator-supplied transcript for an editable diagnosis.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BackgroundTask,
    MediaAsset,
    Publication,
    VideoDiagnosis,
    new_id,
    utc_now,
)
from app.schemas import Actor

AnalysisMode = Literal["full", "partial", "manual"]

VIDEO_STORAGE_ENV = "VIDEO_STORAGE_DIR"
MAX_VIDEO_BYTES = 250 * 1024 * 1024
ALLOWED_VIDEO_MEDIA_TYPES = frozenset(
    {
        "video/mp4",
        "video/quicktime",
        "video/webm",
        "video/x-m4v",
    }
)
ALLOWED_VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".webm", ".m4v"})


@dataclass(frozen=True, slots=True)
class VideoUploadResult:
    asset: MediaAsset
    task: BackgroundTask
    diagnosis: VideoDiagnosis


def save_and_analyze_video(
    db: Session,
    actor: Actor,
    *,
    publication_id: str,
    original_filename: str,
    media_type: str,
    content: bytes,
    manual_transcript: str = "",
    observed_at: datetime | None = None,
    storage_root: str | Path | None = None,
    ffprobe_path: str | None = None,
) -> VideoUploadResult:
    """Persist a private video and create an editable, provenance-rich diagnosis."""

    publication = db.scalar(
        select(Publication).where(
            Publication.id == publication_id,
            Publication.organization_id == actor.organization_id,
        )
    )
    if publication is None:
        raise HTTPException(status_code=404, detail="Publication not found")

    safe_name = Path(original_filename or "video.mp4").name
    normalized_media_type = media_type.strip().lower()
    suffix = Path(safe_name).suffix.lower()
    if (
        normalized_media_type not in ALLOWED_VIDEO_MEDIA_TYPES
        or suffix not in ALLOWED_VIDEO_SUFFIXES
    ):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Supported video formats are MP4, MOV, M4V and WebM",
        )
    if not content:
        raise HTTPException(status_code=422, detail="Video file is empty")
    if len(content) > MAX_VIDEO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Video file must be {MAX_VIDEO_BYTES // (1024 * 1024)} MB or smaller",
        )

    digest = hashlib.sha256(content).hexdigest()
    asset = db.scalar(
        select(MediaAsset).where(
            MediaAsset.organization_id == actor.organization_id,
            MediaAsset.sha256 == digest,
            MediaAsset.deleted_at.is_(None),
        )
    )
    created_asset = asset is None
    if asset is None:
        asset_id = new_id()
        storage_key = f"{actor.organization_id}/{asset_id}{suffix}"
        path = _resolve_storage_path(storage_root, storage_key)
        _write_private_file(path, content)
        asset = MediaAsset(
            id=asset_id,
            organization_id=actor.organization_id,
            purpose="publication_video_analysis",
            original_filename=safe_name,
            media_type=normalized_media_type,
            size_bytes=len(content),
            sha256=digest,
            storage_key=storage_key,
            status="ready",
            metadata_json={"publication_ids": [publication.id]},
            created_by=actor.user_id,
        )
        db.add(asset)
        db.flush()
    else:
        metadata = dict(asset.metadata_json or {})
        publication_ids = list(metadata.get("publication_ids") or [])
        if publication.id not in publication_ids:
            publication_ids.append(publication.id)
        metadata["publication_ids"] = publication_ids
        asset.metadata_json = metadata

    idempotency_key = f"video-analysis:{publication.id}:{asset.sha256}"
    existing_task = db.scalar(
        select(BackgroundTask).where(
            BackgroundTask.organization_id == actor.organization_id,
            BackgroundTask.idempotency_key == idempotency_key,
        )
    )
    if existing_task is not None:
        existing_diagnosis = db.scalar(
            select(VideoDiagnosis)
            .where(
                VideoDiagnosis.organization_id == actor.organization_id,
                VideoDiagnosis.publication_id == publication.id,
                VideoDiagnosis.media_asset_id == asset.id,
            )
            .order_by(VideoDiagnosis.created_at.desc())
        )
        if existing_diagnosis is not None:
            db.commit()
            return VideoUploadResult(
                asset=asset,
                task=existing_task,
                diagnosis=existing_diagnosis,
            )

    task = BackgroundTask(
        organization_id=actor.organization_id,
        task_type="video_analysis",
        idempotency_key=idempotency_key,
        payload={
            "publication_id": publication.id,
            "media_asset_id": asset.id,
            "manual_transcript_supplied": bool(manual_transcript.strip()),
        },
        status="running",
        progress={"stage": "technical_metadata"},
        attempt_count=1,
        created_by=actor.user_id,
        started_at=utc_now(),
    )
    db.add(task)
    db.flush()

    probe = _probe_video(
        _resolve_storage_path(storage_root, asset.storage_key),
        ffprobe_path=ffprobe_path,
    )
    analysis_mode: AnalysisMode = "partial" if probe else "manual"
    findings = _technical_findings(probe)
    if not findings:
        findings = [
            {
                "category": "manual_review",
                "severity": "observation",
                "evidence": "No local technical analyser was available.",
                "recommendation": (
                    "Review the opening, pacing, subtitles and call to action manually, "
                    "or connect an approved analysis provider."
                ),
            }
        ]
    limitations = [
        "No semantic scene understanding was performed.",
        "No automatic speech recognition was performed.",
        "The diagnosis does not predict views, likes or sales.",
    ]
    diagnosis = VideoDiagnosis(
        organization_id=actor.organization_id,
        publication_id=publication.id,
        media_asset_id=asset.id,
        analysis_mode=analysis_mode,
        analysis_metadata={
            "technical_probe": probe,
            "manual_transcript_supplied": bool(manual_transcript.strip()),
            "limitations": limitations,
        },
        observed_at=observed_at or utc_now(),
        title=f"Video review: {safe_name}",
        summary=(
            "Technical metadata was extracted; content-level findings still require "
            "human review."
            if analysis_mode == "partial"
            else "Manual review workspace created; automated video understanding is not connected."
        ),
        transcript_excerpt=manual_transcript.strip()[:4000],
        findings=findings,
        created_by=actor.user_id,
    )
    db.add(diagnosis)
    task.status = "completed"
    task.progress = {
        "stage": "completed",
        "analysis_mode": analysis_mode,
        "diagnosis_id": diagnosis.id,
    }
    task.finished_at = utc_now()

    try:
        db.commit()
    except Exception:
        db.rollback()
        if created_asset:
            _resolve_storage_path(storage_root, asset.storage_key).unlink(missing_ok=True)
        raise
    db.refresh(asset)
    db.refresh(task)
    db.refresh(diagnosis)
    return VideoUploadResult(asset=asset, task=task, diagnosis=diagnosis)


def get_media_asset(db: Session, actor: Actor, asset_id: str) -> MediaAsset:
    asset = db.scalar(
        select(MediaAsset).where(
            MediaAsset.id == asset_id,
            MediaAsset.organization_id == actor.organization_id,
            MediaAsset.deleted_at.is_(None),
        )
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="Media asset not found")
    return asset


def locate_media_asset(
    db: Session,
    actor: Actor,
    asset_id: str,
    *,
    storage_root: str | Path | None = None,
) -> Path:
    asset = get_media_asset(db, actor, asset_id)
    path = _resolve_storage_path(storage_root, asset.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Media file not found")
    if path.stat().st_size != asset.size_bytes:
        raise HTTPException(status_code=409, detail="Media file failed size verification")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != asset.sha256:
        raise HTTPException(status_code=409, detail="Media file failed integrity verification")
    return path


def _technical_findings(probe: dict[str, Any]) -> list[dict[str, str]]:
    if not probe:
        return []
    findings: list[dict[str, str]] = []
    duration = probe.get("duration_seconds")
    if isinstance(duration, (int, float)):
        findings.append(
            {
                "category": "duration",
                "severity": "observation",
                "evidence": f"Technical duration: {duration:.1f} seconds.",
                "recommendation": (
                    "Check that the selected script format and platform pacing match this duration."
                ),
            }
        )
    width = probe.get("width")
    height = probe.get("height")
    if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
        orientation = "vertical" if height > width else "horizontal" if width > height else "square"
        findings.append(
            {
                "category": "frame",
                "severity": "observation",
                "evidence": f"Frame: {width}×{height} ({orientation}).",
                "recommendation": "Confirm the frame orientation matches the target platform.",
            }
        )
    return findings


def _probe_video(path: Path, *, ffprobe_path: str | None) -> dict[str, Any]:
    executable = ffprobe_path or shutil.which("ffprobe")
    if not executable:
        return {}
    try:
        completed = subprocess.run(
            [
                executable,
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type,width,height",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            check=True,
            text=True,
            timeout=15,
        )
        payload = json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        return {}
    streams = payload.get("streams") if isinstance(payload, dict) else None
    video_stream = next(
        (
            stream
            for stream in streams or []
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ),
        {},
    )
    format_data = payload.get("format") if isinstance(payload, dict) else {}
    raw_duration = (format_data or {}).get("duration")
    duration: float | None
    if isinstance(raw_duration, (str, int, float)) and not isinstance(raw_duration, bool):
        try:
            duration = float(raw_duration)
        except ValueError:
            duration = None
    else:
        duration = None
    result: dict[str, Any] = {}
    if duration is not None and duration >= 0:
        result["duration_seconds"] = duration
    for key in ("width", "height"):
        value = video_stream.get(key) if isinstance(video_stream, dict) else None
        if isinstance(value, int) and value > 0:
            result[key] = value
    return result


def _storage_root(storage_root: str | Path | None) -> Path:
    configured = storage_root or os.getenv(VIDEO_STORAGE_ENV)
    if configured is None:
        configured = Path.cwd() / "private" / "videos"
    return Path(configured).expanduser().resolve()


def _resolve_storage_path(storage_root: str | Path | None, storage_key: str) -> Path:
    root = _storage_root(storage_root)
    candidate = (root / Path(storage_key)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Invalid media storage location") from exc
    return candidate


def _write_private_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    temporary = path.with_suffix(path.suffix + f".{new_id()}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = [
    "ALLOWED_VIDEO_MEDIA_TYPES",
    "AnalysisMode",
    "MAX_VIDEO_BYTES",
    "VIDEO_STORAGE_ENV",
    "VideoUploadResult",
    "get_media_asset",
    "locate_media_asset",
    "save_and_analyze_video",
]
