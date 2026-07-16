from datetime import UTC, datetime

from sqlalchemy import select

from app.models import (
    OperationImportRecord,
    PerformanceReview,
    PerformanceSnapshot,
    Publication,
)
from app.operation_feedback import (
    commit_operation_data,
    create_performance_review,
    preview_operation_data,
)
from app.schemas import Actor


def _actor(owner: dict) -> Actor:
    return Actor(
        user_id=owner["user_id"],
        organization_id=owner["organization_id"],
        role="owner",
    )


def _publication(db, owner: dict, *, content_id: str = "tomato-001") -> Publication:
    publication = Publication(
        organization_id=owner["organization_id"],
        project_id="project-for-operation-test",
        content_version_id="version-for-operation-test",
        platform="douyin",
        external_url="https://www.douyin.com/video/tomato-001",
        external_content_id=content_id,
        published_at=datetime.now(UTC),
        note="",
        created_by=owner["user_id"],
    )
    db.add(publication)
    db.commit()
    db.refresh(publication)
    return publication


def test_preview_and_commit_match_only_exact_publication_key(db, owner) -> None:
    publication = _publication(db, owner)
    content = (
        "平台,作品ID,播放量,点赞数,评论数,分享数,销售额,币种\n"
        "抖音,tomato-001,1200,80,12,9,199.50,CNY\n"
        "抖音,unknown-002,300,10,0,0,0,CNY\n"
    ).encode()

    preview = preview_operation_data(
        db,
        _actor(owner),
        content,
        filename="番茄运营数据.csv",
    )

    assert preview.matched_publication_ids == (publication.id, None)
    batch = commit_operation_data(
        db,
        _actor(owner),
        content,
        filename="番茄运营数据.csv",
    )
    assert batch.status == "completed"
    assert batch.imported_rows == 1
    rows = list(
        db.scalars(select(OperationImportRecord).order_by(OperationImportRecord.row_number))
    )
    assert [row.status for row in rows] == ["imported", "unmatched"]
    snapshot = db.scalar(select(PerformanceSnapshot))
    assert snapshot is not None
    assert snapshot.publication_id == publication.id
    assert snapshot.views == 1200
    assert snapshot.revenue_minor == 19950
    assert snapshot.capture_method == "file_import"


def test_rule_based_review_states_limitations(db, owner) -> None:
    publication = _publication(db, owner)
    snapshot = PerformanceSnapshot(
        organization_id=owner["organization_id"],
        publication_id=publication.id,
        captured_at=datetime.now(UTC),
        views=100,
        likes=10,
        comments=0,
        shares=0,
        saves=3,
        clicks=2,
        followers_gained=1,
        orders=1,
        revenue_minor=5000,
        currency="CNY",
        extra_metrics={},
        capture_method="manual",
        note="",
        created_by=owner["user_id"],
    )
    db.add(snapshot)
    db.commit()

    review = create_performance_review(db, _actor(owner), publication.id)

    assert review.methodology == "rule-based-v1"
    assert any(signal["metric"] == "点赞率" for signal in review.signals)
    assert {item["area"] for item in review.recommendations} == {
        "分享动机",
        "互动问题",
    }
    assert "不代表平台归因" in review.limitations[0]
    assert db.scalar(select(PerformanceReview).where(PerformanceReview.id == review.id))
