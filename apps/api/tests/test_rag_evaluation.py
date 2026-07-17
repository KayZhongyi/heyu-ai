from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.rag_evaluation import evaluate_dataset, load_dataset, write_report

ROOT = Path(__file__).resolve().parents[3]
DATASET_PATH = ROOT / "evals" / "rag-citations" / "dataset-v1.json"
CLI_PATH = ROOT / "scripts" / "evaluate-rag-citations.py"


def test_checked_in_dataset_covers_languages_documents_locators_and_fallback():
    loaded = load_dataset(DATASET_PATH)

    report = evaluate_dataset(
        loaded.payload,
        dataset_sha256=loaded.sha256,
        dataset_path=loaded.path,
        generated_at=datetime(2026, 7, 17, tzinfo=UTC),
    )

    assert report["passed"] is True
    assert report["offline"] is True
    assert report["paid_api_calls"] == 0
    assert report["dataset"]["case_count"] == 6
    assert report["dataset"]["sha256"] == loaded.sha256
    assert report["coverage"] == {
        "locales": ["en", "zh-CN", "zh-HK"],
        "document_types": ["docx", "pdf", "pptx"],
        "locator_types": ["page", "paragraph", "slide"],
        "strategies": ["lexical-v1-fallback"],
        "fallback_reasons": ["query-embedding-unavailable"],
    }
    assert report["aggregate"]["recall_at_k"] == {
        "1": 1.0,
        "3": 1.0,
        "5": 1.0,
    }
    assert report["aggregate"]["mrr"] == 1.0
    assert report["aggregate"]["locator_accuracy"] == 1.0
    assert all(
        case["observed"]["first_relevant_locator"][case["locator_type"]]
        == case["expected"]["locator"][case["locator_type"]]
        for case in report["cases"]
    )


def test_metrics_measure_rank_and_locator_accuracy_independently():
    dataset = {
        "dataset_version": "metric-test-v1",
        "top_ks": [1, 2],
        "thresholds": {
            "minimum_recall_at_k": {"1": 0.0, "2": 1.0},
            "minimum_mrr": 0.5,
            "minimum_locator_accuracy": 1.0,
        },
        "cases": [
            {
                "case_id": "rank-two",
                "locale": "en",
                "document_type": "pdf",
                "query": "shared term",
                "relevant_chunk_ids": ["relevant"],
                "expected_locator": {"page": 9},
                "expected_strategy": "lexical-v1-fallback",
                "candidates": [
                    {
                        "chunk_id": "first",
                        "text": "shared term shared term",
                        "locator": {"page": 1},
                    },
                    {
                        "chunk_id": "relevant",
                        "text": "shared term",
                        "locator": {"page": 9},
                    },
                ],
            },
            {
                "case_id": "coverage-zh-hk-pptx",
                "locale": "zh-HK",
                "document_type": "pptx",
                "query": "荔枝",
                "relevant_chunk_ids": ["slide"],
                "expected_locator": {"slide": 2},
                "candidates": [
                    {
                        "chunk_id": "slide",
                        "text": "荔枝",
                        "locator": {"slide": 2},
                    }
                ],
            },
            {
                "case_id": "coverage-zh-cn-docx",
                "locale": "zh-CN",
                "document_type": "docx",
                "query": "番茄",
                "relevant_chunk_ids": ["paragraph"],
                "expected_locator": {"paragraph": 3},
                "candidates": [
                    {
                        "chunk_id": "paragraph",
                        "text": "番茄",
                        "locator": {"paragraph": 3},
                    }
                ],
            },
        ],
    }

    report = evaluate_dataset(dataset)
    ranked_case = report["cases"][0]

    assert ranked_case["metrics"]["recall_at_k"] == {"1": 0.0, "2": 1.0}
    assert ranked_case["metrics"]["reciprocal_rank"] == 0.5
    assert ranked_case["metrics"]["locator_accuracy"] == 1.0
    assert report["aggregate"]["mrr"] == pytest.approx((0.5 + 1 + 1) / 3)


def test_locator_accuracy_fails_when_the_relevant_chunk_has_the_wrong_locator():
    loaded = load_dataset(DATASET_PATH)
    dataset = json.loads(json.dumps(loaded.payload))
    dataset["cases"][0]["expected_locator"] = {"page": 99}
    dataset["thresholds"]["minimum_locator_accuracy"] = 1.0

    report = evaluate_dataset(dataset)

    assert report["aggregate"]["recall_at_k"]["1"] == 1.0
    assert report["aggregate"]["locator_accuracy"] < 1.0
    assert report["checks"]["metrics"]["locator_accuracy"] is False
    assert report["passed"] is False


def test_expected_retrieval_strategy_is_part_of_the_pass_decision():
    loaded = load_dataset(DATASET_PATH)
    dataset = json.loads(json.dumps(loaded.payload))
    case_id = dataset["cases"][0]["case_id"]
    dataset["cases"][0]["expected_strategy"] = "hybrid-v1"

    report = evaluate_dataset(dataset)

    assert report["aggregate"]["strategy_match_rate"] < 1.0
    assert report["checks"]["strategy"][case_id] is False
    assert report["passed"] is False


def test_report_writer_produces_round_trippable_audit_json(tmp_path: Path):
    loaded = load_dataset(DATASET_PATH)
    report = evaluate_dataset(
        loaded.payload,
        dataset_sha256=loaded.sha256,
        dataset_path=loaded.path,
    )
    output = tmp_path / "audit" / "rag-report.json"

    write_report(output, report)

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["dataset"]["sha256"] == loaded.sha256
    assert persisted["aggregate"] == report["aggregate"]
    assert persisted["cases"][0]["results"][0]["text_sha256"]


def test_cli_runs_offline_and_writes_auditable_json(tmp_path: Path):
    output = tmp_path / "rag-citation-evaluation.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(CLI_PATH),
            "--dataset",
            str(DATASET_PATH),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    summary = json.loads(completed.stdout)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert summary["passed"] is True
    assert summary["mrr"] == 1.0
    assert summary["locator_accuracy"] == 1.0
    assert report["passed"] is True
    assert report["dataset"]["sha256"]
