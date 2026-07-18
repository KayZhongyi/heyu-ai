"""Persisted wrapper around the versioned offline marketing quality evaluator."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EvaluationRun, utc_now
from app.schemas import Actor


def _find_repository_root(module_path: Path) -> Path:
    configured_root = os.getenv("HEYU_REPOSITORY_ROOT", "").strip()
    if configured_root:
        return Path(configured_root).expanduser().resolve()

    resolved_module = module_path.resolve()
    for parent in resolved_module.parents:
        if (parent / "scripts" / "evaluate-content-quality.py").is_file():
            return parent
    return Path.cwd().resolve()


REPOSITORY_ROOT = _find_repository_root(Path(__file__))
EVALUATOR_SCRIPT = REPOSITORY_ROOT / "scripts" / "evaluate-content-quality.py"


def run_offline_marketing_evaluation(
    db: Session,
    actor: Actor,
    *,
    timeout_seconds: int = 120,
) -> EvaluationRun:
    """Run the checked-in dataset and baseline without calling an external model."""

    run = EvaluationRun(
        organization_id=actor.organization_id,
        evaluation_type="offline_marketing_rules",
        dataset_version="pending",
        evaluator_version="pending",
        status="running",
        created_by=actor.user_id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        with tempfile.TemporaryDirectory(prefix="heyu-quality-") as temp_dir:
            output_path = Path(temp_dir) / "report.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(EVALUATOR_SCRIPT),
                    "--output",
                    str(output_path),
                ],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            if not output_path.is_file():
                detail = _safe_process_error(completed)
                raise RuntimeError(detail or "Evaluator did not produce a report")
            report = json.loads(output_path.read_text(encoding="utf-8"))
            _validate_report(report)
    except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as exc:
        run.status = "failed"
        run.error = str(exc)[:4000]
        run.finished_at = utc_now()
        db.commit()
        db.refresh(run)
        return run

    run.dataset_version = str(report["dataset_version"])
    run.evaluator_version = str(report["evaluator_version"])
    run.status = "completed"
    run.passed = bool(
        report["passed"] and report.get("baseline_comparison", {}).get("passed", False)
    )
    run.overall_score = float(report["aggregate"]["overall_score"])
    run.report = report
    run.error = "" if completed.returncode in {0, 1} else _safe_process_error(completed)
    run.finished_at = utc_now()
    db.commit()
    db.refresh(run)
    return run


def list_evaluation_runs(db: Session, actor: Actor) -> list[EvaluationRun]:
    return list(
        db.scalars(
            select(EvaluationRun)
            .where(EvaluationRun.organization_id == actor.organization_id)
            .order_by(EvaluationRun.created_at.desc(), EvaluationRun.id.desc())
        )
    )


def get_evaluation_run(db: Session, actor: Actor, run_id: str) -> EvaluationRun:
    run = db.scalar(
        select(EvaluationRun).where(
            EvaluationRun.id == run_id,
            EvaluationRun.organization_id == actor.organization_id,
        )
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return run


def _validate_report(report: Any) -> None:
    if not isinstance(report, dict):
        raise ValueError("Evaluator returned an invalid report")
    required = {"dataset_version", "evaluator_version", "passed", "aggregate"}
    if not required.issubset(report):
        raise ValueError("Evaluator report is missing required fields")
    aggregate = report.get("aggregate")
    if not isinstance(aggregate, dict) or not isinstance(
        aggregate.get("overall_score"),
        (int, float),
    ):
        raise ValueError("Evaluator report has an invalid aggregate score")


def _safe_process_error(completed: subprocess.CompletedProcess[str]) -> str:
    return (completed.stderr or completed.stdout or "").strip()[:4000]


__all__ = [
    "EVALUATOR_SCRIPT",
    "get_evaluation_run",
    "list_evaluation_runs",
    "run_offline_marketing_evaluation",
]
