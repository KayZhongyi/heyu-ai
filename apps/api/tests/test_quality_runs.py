from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app import quality_runs
from app.models import Organization, Role, User
from app.quality_runs import (
    get_evaluation_run,
    list_evaluation_runs,
    run_offline_marketing_evaluation,
)
from app.schemas import Actor


def test_repository_root_falls_back_safely_when_evaluator_is_not_bundled(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.chdir(tmp_path)

    assert quality_runs._find_repository_root(tmp_path / "app" / "quality_runs.py") == tmp_path


def _actor(db: Session, slug: str) -> Actor:
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
        role=Role.owner,
    )


def test_offline_quality_run_is_persisted_with_versioned_report(db: Session):
    actor = _actor(db, "quality-owner")

    run = run_offline_marketing_evaluation(db, actor)

    assert run.status == "completed"
    assert run.dataset_version == "marketing-offline-v1"
    assert run.evaluator_version == "marketing-rules-v2"
    assert isinstance(run.passed, bool)
    assert run.overall_score is not None
    assert "do not predict or guarantee" in run.report["disclaimer"]
    assert get_evaluation_run(db, actor, run.id).id == run.id
    assert [item.id for item in list_evaluation_runs(db, actor)] == [run.id]


def test_evaluator_failure_is_recorded_without_fabricated_scores(
    db: Session,
    monkeypatch,
    tmp_path: Path,
):
    actor = _actor(db, "quality-failure")
    monkeypatch.setattr(quality_runs, "EVALUATOR_SCRIPT", tmp_path / "missing.py")

    run = run_offline_marketing_evaluation(db, actor)

    assert run.status == "failed"
    assert run.passed is None
    assert run.overall_score is None
    assert run.report == {}
    assert run.error


def test_evaluation_runs_are_tenant_isolated(db: Session):
    owner = _actor(db, "quality-tenant-owner")
    outsider = _actor(db, "quality-tenant-outsider")
    run = run_offline_marketing_evaluation(db, owner)

    assert list_evaluation_runs(db, outsider) == []
    try:
        get_evaluation_run(db, outsider, run.id)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 404
    else:
        raise AssertionError("Tenant boundary did not hide the evaluation run")
