"""Generate exact-commit release evidence from Git, GitHub Actions, and local checks."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
EXPECTED_JOBS = (
    "api",
    "browser-e2e",
    "docker-build",
    "repository-audit",
    "windows-package",
)


class EvidenceError(RuntimeError):
    """Raised when exact-commit evidence cannot be established."""


def run(
    command: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "no command output"
        raise EvidenceError(f"{' '.join(command)} failed: {detail}")
    return result.stdout.strip()


def git_value(*arguments: str) -> str:
    return run(["git", *arguments])


def repository_slug() -> str:
    url = git_value("remote", "get-url", "origin").strip()
    match = re.search(r"github\.com[/:](?P<slug>[^/]+/[^/]+?)(?:\.git)?$", url)
    if not match:
        raise EvidenceError("origin is not a recognizable GitHub repository URL")
    return match.group("slug")


def parse_test_count(output: str) -> int:
    summary_matches = re.findall(r"(?m)(\d+)\s+(?:tests?|items?)\s+collected\b", output)
    if summary_matches:
        return int(summary_matches[-1])

    file_counts = [
        int(match)
        for match in re.findall(r"(?m)^tests[/\\][^:\r\n]+:\s*(\d+)\s*$", output)
    ]
    if file_counts:
        return sum(file_counts)
    raise EvidenceError("pytest collection output did not contain a test count")


def collect_test_count() -> int:
    output = run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=API_ROOT,
    )
    return parse_test_count(output)


def collect_migration_heads() -> list[str]:
    env = os.environ.copy()
    env.setdefault("DATABASE_URL", "sqlite://")
    output = run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=API_ROOT,
        env=env,
    )
    heads = re.findall(r"(?m)^([0-9a-z]+)\s+\(head\)\s*$", output)
    if not heads:
        raise EvidenceError("Alembic did not report a migration head")
    return heads


def find_run_id(commit_sha: str) -> int:
    payload = json.loads(
        run(
            [
                "gh",
                "run",
                "list",
                "--commit",
                commit_sha,
                "--workflow",
                "CI",
                "--event",
                "push",
                "--limit",
                "20",
                "--json",
                "databaseId,headSha,status,conclusion,event,workflowName,createdAt",
            ]
        )
    )
    matching = [
        item
        for item in payload
        if item.get("headSha") == commit_sha
        and item.get("workflowName") == "CI"
        and item.get("event") == "push"
    ]
    if not matching:
        raise EvidenceError(f"no CI push run found for exact commit {commit_sha}")
    matching.sort(key=lambda item: item.get("createdAt", ""), reverse=True)
    return int(matching[0]["databaseId"])


def load_run(run_id: int) -> dict[str, Any]:
    return json.loads(
        run(
            [
                "gh",
                "run",
                "view",
                str(run_id),
                "--json",
                (
                    "databaseId,headSha,status,conclusion,event,workflowName,"
                    "createdAt,updatedAt,url,jobs"
                ),
            ]
        )
    )


def validate_ci_run(
    payload: dict[str, Any],
    *,
    commit_sha: str,
    expected_jobs: tuple[str, ...] = EXPECTED_JOBS,
) -> list[dict[str, Any]]:
    if payload.get("headSha") != commit_sha:
        raise EvidenceError("GitHub Actions run does not belong to the exact commit")
    if payload.get("workflowName") != "CI" or payload.get("event") != "push":
        raise EvidenceError("evidence requires the CI workflow's push run")
    if payload.get("status") != "completed" or payload.get("conclusion") != "success":
        raise EvidenceError("exact-commit CI run is not completed successfully")

    jobs = {
        item.get("name"): item
        for item in payload.get("jobs", [])
        if isinstance(item, dict) and item.get("name")
    }
    missing = sorted(set(expected_jobs) - set(jobs))
    if missing:
        raise EvidenceError(f"CI run is missing required jobs: {', '.join(missing)}")
    unsuccessful = sorted(
        name
        for name in expected_jobs
        if jobs[name].get("status") != "completed"
        or jobs[name].get("conclusion") != "success"
    )
    if unsuccessful:
        raise EvidenceError(
            f"required CI jobs are not successful: {', '.join(unsuccessful)}"
        )
    return [
        {
            "name": name,
            "status": jobs[name]["status"],
            "conclusion": jobs[name]["conclusion"],
            "url": jobs[name].get("url"),
        }
        for name in expected_jobs
    ]


def build_evidence(
    *,
    commit_sha: str,
    branch: str,
    slug: str,
    dirty: bool,
    ci_run: dict[str, Any],
    test_count: int,
    migration_heads: list[str],
) -> dict[str, Any]:
    jobs = validate_ci_run(ci_run, commit_sha=commit_sha)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "repository": {
            "slug": slug,
            "branch": branch,
            "commit_sha": commit_sha,
            "worktree_dirty": dirty,
        },
        "ci": {
            "workflow": ci_run["workflowName"],
            "run_id": ci_run["databaseId"],
            "url": ci_run["url"],
            "event": ci_run["event"],
            "status": ci_run["status"],
            "conclusion": ci_run["conclusion"],
            "created_at": ci_run["createdAt"],
            "updated_at": ci_run["updatedAt"],
            "required_jobs": list(EXPECTED_JOBS),
            "jobs": jobs,
            "gate_passed": True,
        },
        "local_verification": {
            "python_tests_collected": test_count,
            "migration_heads": migration_heads,
        },
        "human_acceptance": {
            "status": "not_verified",
            "note": (
                "Automated exact-commit evidence does not replace the retained "
                "human acceptance record."
            ),
        },
        "result": "automated_evidence_passed",
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Generate exact-commit CI and local release evidence."
    )
    result.add_argument(
        "--run-id",
        type=int,
        help="Specific GitHub Actions run ID; otherwise resolve the exact commit.",
    )
    result.add_argument(
        "--output",
        type=Path,
        help=(
            "JSON destination. Defaults to outputs/release-evidence/<commit-sha>.json."
        ),
    )
    result.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow generation from a dirty tree while recording that state.",
    )
    return result


def main() -> int:
    arguments = parser().parse_args()
    try:
        commit_sha = git_value("rev-parse", "HEAD")
        branch = git_value("branch", "--show-current") or "(detached)"
        dirty = bool(git_value("status", "--porcelain"))
        if dirty and not arguments.allow_dirty:
            raise EvidenceError(
                "worktree is dirty; commit or stash changes before attributing "
                "local verification to HEAD"
            )

        run_id = arguments.run_id or find_run_id(commit_sha)
        ci_run = load_run(run_id)
        evidence = build_evidence(
            commit_sha=commit_sha,
            branch=branch,
            slug=repository_slug(),
            dirty=dirty,
            ci_run=ci_run,
            test_count=collect_test_count(),
            migration_heads=collect_migration_heads(),
        )
        output = arguments.output or (
            ROOT / "outputs" / "release-evidence" / f"{commit_sha}.json"
        )
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (EvidenceError, json.JSONDecodeError) as exc:
        print(f"Release evidence failed: {exc}", file=sys.stderr)
        return 1

    print(f"Release evidence written to {output}")
    print(
        f"Exact commit {commit_sha}: CI run {run_id}, "
        f"{evidence['local_verification']['python_tests_collected']} tests collected."
    )
    print("Human acceptance remains a separate required gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
