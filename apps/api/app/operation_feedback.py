"""Persistence services for operation-data imports and explainable feedback."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    OperationImportBatch,
    OperationImportRecord,
    PerformanceReview,
    PerformanceSnapshot,
    Publication,
)
from app.operation_imports import (
    OperationImportError,
    OperationImportResult,
    parse_operation_import,
)
from app.schemas import Actor


@dataclass(frozen=True, slots=True)
class ImportPreview:
    result: OperationImportResult
    matched_publication_ids: tuple[str | None, ...]


def preview_operation_data(
    db: Session,
    actor: Actor,
    data: bytes,
    *,
    filename: str,
    media_type: str | None = None,
    field_mapping: dict[str, str] | None = None,
) -> ImportPreview:
    existing = tuple(
        db.scalars(
            select(OperationImportRecord.source_fingerprint).where(
                OperationImportRecord.organization_id == actor.organization_id
            )
        )
    )
    result = parse_operation_import(
        data,
        filename=filename,
        media_type=media_type,
        field_mapping=field_mapping,
        existing_fingerprints=existing,
    )
    matches = tuple(
        _match_publication(db, actor, row.normalized)
        if row.is_valid and not row.duplicate
        else None
        for row in result.rows
    )
    return ImportPreview(
        result=result,
        matched_publication_ids=tuple(item.id if item else None for item in matches),
    )


def commit_operation_data(
    db: Session,
    actor: Actor,
    data: bytes,
    *,
    filename: str,
    media_type: str | None = None,
    field_mapping: dict[str, str] | None = None,
) -> OperationImportBatch:
    preview = preview_operation_data(
        db,
        actor,
        data,
        filename=filename,
        media_type=media_type,
        field_mapping=field_mapping,
    )
    result = preview.result
    batch = OperationImportBatch(
        organization_id=actor.organization_id,
        original_filename=filename[:255],
        media_type=(media_type or "")[:120],
        file_sha256=hashlib.sha256(data).hexdigest(),
        field_mapping=dict(result.field_mapping),
        warnings=list(result.warnings),
        status="committing",
        total_rows=len(result.rows),
        valid_rows=len(result.valid_rows),
        invalid_rows=len(result.invalid_rows),
        created_by=actor.user_id,
    )
    db.add(batch)
    db.flush()

    imported = 0
    duplicates = 0
    for row, publication_id in zip(
        result.rows,
        preview.matched_publication_ids,
        strict=True,
    ):
        if row.duplicate:
            duplicates += 1
            continue
        errors = [
            {
                "code": error.code,
                "message": error.message,
                "field": error.field,
                "value": error.value,
            }
            for error in row.errors
        ]
        normalized = _json_safe(row.normalized)
        status = "invalid" if errors else "unmatched" if publication_id is None else "matched"
        record = OperationImportRecord(
            organization_id=actor.organization_id,
            batch_id=batch.id,
            publication_id=publication_id,
            row_number=row.row_number,
            source_fingerprint=row.source_fingerprint,
            normalized=normalized,
            errors=errors,
            status=status,
        )
        db.add(record)
        db.flush()
        if status != "matched" or publication_id is None:
            continue
        try:
            snapshot = _snapshot_from_row(actor, publication_id, row.normalized)
        except OperationImportError as exc:
            record.status = "invalid"
            record.errors = [{"code": exc.code, "message": exc.detail}]
            continue
        db.add(snapshot)
        db.flush()
        record.performance_snapshot_id = snapshot.id
        record.status = "imported"
        imported += 1

    batch.imported_rows = imported
    batch.duplicate_rows = duplicates
    batch.status = "completed"
    batch.committed_at = datetime.now(UTC)
    db.commit()
    db.refresh(batch)
    return batch


def create_performance_review(
    db: Session,
    actor: Actor,
    publication_id: str,
) -> PerformanceReview:
    publication = db.scalar(
        select(Publication).where(
            Publication.id == publication_id,
            Publication.organization_id == actor.organization_id,
        )
    )
    if publication is None:
        raise HTTPException(status_code=404, detail="Publication not found")
    snapshots = list(
        db.scalars(
            select(PerformanceSnapshot)
            .where(
                PerformanceSnapshot.publication_id == publication.id,
                PerformanceSnapshot.organization_id == actor.organization_id,
            )
            .order_by(PerformanceSnapshot.captured_at.desc())
            .limit(2)
        )
    )
    if not snapshots:
        raise HTTPException(
            status_code=409,
            detail="Import or enter at least one performance snapshot first",
        )
    latest = snapshots[0]
    previous = snapshots[1] if len(snapshots) > 1 else None
    signals, recommendations = _review_signals(latest, previous)
    review = PerformanceReview(
        organization_id=actor.organization_id,
        publication_id=publication.id,
        latest_snapshot_id=latest.id,
        methodology="rule-based-v1",
        summary=_review_summary(latest, previous),
        signals=signals,
        recommendations=recommendations,
        limitations=[
            "规则分析只描述已导入数据，不代表平台归因或未来传播保证。",
            "没有曝光、完播率或受众留存数据时，不推断视频内容被完整观看。",
        ],
        created_by=actor.user_id,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


def _match_publication(
    db: Session,
    actor: Actor,
    normalized: dict[str, Any] | Any,
) -> Publication | None:
    platform = str(normalized.get("platform", ""))
    content_id = str(normalized.get("external_content_id", ""))
    external_url = str(normalized.get("external_url", ""))
    predicates = [
        Publication.organization_id == actor.organization_id,
        Publication.platform == platform,
    ]
    if content_id:
        predicates.append(Publication.external_content_id == content_id)
    elif external_url:
        predicates.append(Publication.external_url == external_url)
    else:
        return None
    matches = list(db.scalars(select(Publication).where(*predicates).limit(2)))
    if len(matches) > 1:
        raise HTTPException(
            status_code=409,
            detail="More than one publication has the same exact platform key",
        )
    return matches[0] if matches else None


def _snapshot_from_row(
    actor: Actor,
    publication_id: str,
    normalized: Any,
) -> PerformanceSnapshot:
    def count(name: str) -> int | None:
        value = normalized.get(name)
        if value is None:
            return None
        decimal = Decimal(value)
        if decimal != decimal.to_integral_value():
            raise OperationImportError(f"{name} must be a whole-number count")
        return int(decimal)

    amount = normalized.get("revenue_amount")
    revenue_minor = (
        int((Decimal(amount) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if amount is not None
        else None
    )
    return PerformanceSnapshot(
        organization_id=actor.organization_id,
        publication_id=publication_id,
        captured_at=datetime.now(UTC),
        views=count("views"),
        likes=count("likes"),
        comments=count("comments"),
        shares=count("shares"),
        saves=count("saves"),
        clicks=count("clicks"),
        followers_gained=count("followers_gained"),
        orders=count("orders"),
        revenue_minor=revenue_minor,
        currency=str(normalized.get("currency", "CNY")),
        extra_metrics=_json_safe(normalized.get("extra_metrics", {})),
        capture_method="file_import",
        note="Imported from CSV/XLSX by exact publication key.",
        created_by=actor.user_id,
    )


def _review_signals(
    latest: PerformanceSnapshot,
    previous: PerformanceSnapshot | None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    views = latest.views or 0
    signals: list[dict[str, Any]] = []
    recommendations: list[dict[str, str]] = []
    if views:
        for metric, value in (
            ("点赞率", latest.likes),
            ("评论率", latest.comments),
            ("分享率", latest.shares),
            ("收藏率", latest.saves),
            ("点击率", latest.clicks),
        ):
            if value is not None:
                signals.append(
                    {
                        "metric": metric,
                        "value": round(value / views, 4),
                        "basis": f"{value}/{views}",
                    }
                )
    if previous and previous.views is not None and latest.views is not None:
        signals.append(
            {
                "metric": "播放量变化",
                "value": latest.views - previous.views,
                "basis": "latest-minus-previous",
            }
        )
    if latest.shares is not None and latest.shares == 0:
        recommendations.append(
            {
                "area": "分享动机",
                "action": "下一版增加可转发的实用信息，例如挑选、保存或食用方法。",
            }
        )
    if latest.comments is not None and latest.comments == 0:
        recommendations.append(
            {
                "area": "互动问题",
                "action": "结尾改成一个容易回答的具体问题，而不是泛化地要求留言。",
            }
        )
    if not recommendations:
        recommendations.append(
            {
                "area": "下一轮测试",
                "action": "保留产品事实，只更换开头钩子或封面文案，避免同时改变过多变量。",
            }
        )
    return signals, recommendations


def _review_summary(
    latest: PerformanceSnapshot,
    previous: PerformanceSnapshot | None,
) -> str:
    if previous is None:
        return "已建立首个运营基线；建议下一轮只测试一个内容变量。"
    if latest.views is None or previous.views is None:
        return "已有多次数据记录，但缺少可比较的播放量，暂不判断传播变化。"
    change = latest.views - previous.views
    if change > 0:
        return f"最新记录的播放量较上一记录增加 {change}，仍需结合发布时间与投放情况判断。"
    if change < 0:
        return f"最新记录的播放量较上一记录减少 {abs(change)}，建议先复查开头与封面。"
    return "两次记录的播放量相同，建议下一轮只替换一个创意变量进行测试。"


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value.normalize() if value else Decimal("0"), "f")
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value
