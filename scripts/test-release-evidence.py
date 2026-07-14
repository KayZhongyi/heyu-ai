"""Self-tests for the exact-commit release evidence generator."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).with_name("release-evidence.py")
SPEC = importlib.util.spec_from_file_location("release_evidence", SCRIPT)
assert SPEC and SPEC.loader
release_evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_evidence)


def sample_run() -> dict:
    return {
        "databaseId": 123,
        "headSha": "a" * 40,
        "status": "completed",
        "conclusion": "success",
        "event": "push",
        "workflowName": "CI",
        "createdAt": "2026-07-14T00:00:00Z",
        "updatedAt": "2026-07-14T00:10:00Z",
        "url": "https://example.invalid/actions/runs/123",
        "jobs": [
            {
                "name": name,
                "status": "completed",
                "conclusion": "success",
                "url": f"https://example.invalid/jobs/{index}",
            }
            for index, name in enumerate(release_evidence.EXPECTED_JOBS, start=1)
        ],
    }


def expect_error(callable_object, expected_text: str) -> None:
    try:
        callable_object()
    except release_evidence.EvidenceError as exc:
        assert expected_text in str(exc), str(exc)
    else:
        raise AssertionError(f"Expected EvidenceError containing {expected_text!r}")


assert release_evidence.parse_test_count("133 tests collected in 1.2s") == 133
assert (
    release_evidence.parse_test_count(
        "tests/test_auth.py: 2\ntests/test_content.py: 5\nwarnings summary\n"
    )
    == 7
)
expect_error(lambda: release_evidence.parse_test_count("no tests here"), "test count")

run = sample_run()
jobs = release_evidence.validate_ci_run(run, commit_sha="a" * 40)
assert [job["name"] for job in jobs] == list(release_evidence.EXPECTED_JOBS)

wrong_commit = sample_run()
wrong_commit["headSha"] = "b" * 40
expect_error(
    lambda: release_evidence.validate_ci_run(
        wrong_commit,
        commit_sha="a" * 40,
    ),
    "exact commit",
)

missing_job = sample_run()
missing_job["jobs"] = missing_job["jobs"][:-1]
expect_error(
    lambda: release_evidence.validate_ci_run(
        missing_job,
        commit_sha="a" * 40,
    ),
    "missing required jobs",
)

failed_job = sample_run()
failed_job["jobs"][0]["conclusion"] = "failure"
expect_error(
    lambda: release_evidence.validate_ci_run(
        failed_job,
        commit_sha="a" * 40,
    ),
    "not successful",
)

evidence = release_evidence.build_evidence(
    commit_sha="a" * 40,
    branch="main",
    slug="example/heyu-ai",
    dirty=False,
    ci_run=sample_run(),
    test_count=133,
    migration_heads=["e8f9a0b1c2d3"],
)
assert evidence["result"] == "automated_evidence_passed"
assert evidence["ci"]["gate_passed"] is True
assert evidence["human_acceptance"]["status"] == "not_verified"
assert evidence["repository"]["commit_sha"] == "a" * 40

print("Release evidence self-tests passed.")
