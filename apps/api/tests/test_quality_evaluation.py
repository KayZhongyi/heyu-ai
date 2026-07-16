from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "scripts" / "evaluate-content-quality.py"
DATASET_PATH = ROOT / "evals" / "marketing" / "dataset-v1.json"
BASELINE_PATH = ROOT / "evals" / "marketing" / "baseline-v2.json"


def _load_evaluator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("quality_evaluator", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def evaluator() -> ModuleType:
    return _load_evaluator()


@pytest.fixture(scope="module")
def dataset(evaluator: ModuleType) -> dict:
    return evaluator.load_dataset(DATASET_PATH)


def test_dataset_is_versioned_deidentified_and_trilingual(dataset: dict):
    assert dataset["dataset_version"] == "marketing-offline-v1"
    assert {case["locale"] for case in dataset["cases"]} == {"zh-CN", "zh-HK", "en"}
    assert len({case["case_key"] for case in dataset["cases"]}) == 3
    serialized = json.dumps(dataset, ensure_ascii=False)
    assert "@" not in serialized
    assert "手机号" not in serialized
    assert "身份证" not in serialized
    assert "规则评分" in dataset["disclaimer"]
    assert "传播效果" in dataset["disclaimer"]


def test_offline_baseline_passes_without_fabricating_usage(evaluator: ModuleType, dataset: dict):
    report = evaluator.run_evaluation(dataset)

    assert report["passed"] is True
    assert report["aggregate"]["case_count"] == 3
    assert report["aggregate"]["passed_case_count"] == 3
    assert set(report["aggregate"]["dimension_scores"]) == set(evaluator.DIMENSIONS)
    assert "do not predict or guarantee" in report["disclaimer"]
    for case in report["cases"]:
        assert case["generation"]["provider"] == "mock"
        assert case["measurements"]["latency_ms"] is not None
        assert case["measurements"]["input_tokens"] is None
        assert case["measurements"]["output_tokens"] is None
        assert case["measurements"]["estimated_cost"] is None
        assert case["measurements"]["currency"] is None
        assert case["measurements"]["token_and_cost_status"] == "unknown"


def test_schema_and_fact_rules_detect_regressions(evaluator: ModuleType, dataset: dict):
    case = dataset["cases"][0]
    generated = evaluator.DeterministicMarketingProvider().generate(
        evaluator.MarketingPlanRequest.model_validate(case["request"])
    )
    payload = generated.model_dump(mode="json")

    malformed = copy.deepcopy(payload)
    malformed["videos"] = malformed["videos"][:1]
    malformed_result = evaluator.evaluate_output(case, malformed)
    assert malformed_result["rules"]["schema"]["score"] == 0

    fact_removed = json.loads(
        json.dumps(payload, ensure_ascii=False)
        .replace("当季番茄", "示例产品")
        .replace("自然成熟", "示例特点甲")
        .replace("清甜多汁", "示例特点乙")
        .replace("当天分选", "示例特点丙")
    )
    fact_result = evaluator.evaluate_output(case, fact_removed)
    assert fact_result["rules"]["factual_grounding"]["score"] == 0
    assert set(fact_result["rules"]["factual_grounding"]["details"]["missing"]) == set(
        case["expected_facts"]
    )


def test_prohibited_claim_and_unknown_citation_are_rejected(evaluator: ModuleType, dataset: dict):
    case = dataset["cases"][0]
    generated = evaluator.DeterministicMarketingProvider().generate(
        evaluator.MarketingPlanRequest.model_validate(case["request"])
    )
    payload = generated.model_dump(mode="json")
    payload["videos"][0]["script"] += " 百分之百有效。"

    claim_result = evaluator.evaluate_output(case, payload)
    assert claim_result["rules"]["prohibited_claims"]["score"] == 0
    assert claim_result["rules"]["prohibited_claims"]["details"]["matched"]

    citation_rule = evaluator._evaluate_citations(
        case,
        {"citations": [{"source_id": "unapproved-source"}]},
    )
    assert citation_rule["score"] == 0
    assert citation_rule["details"]["unknown_source_ids"] == ["unapproved-source"]


def test_language_rules_reject_simplified_copy_for_hong_kong_chinese(
    evaluator: ModuleType, dataset: dict
):
    case = next(item for item in dataset["cases"] if item["locale"] == "zh-HK")
    simplified_copy = {
        "text": ("这个视频帮助用户选择真实产品，农户发布以后查看数据、评论、价格和发货问题。" * 20)
    }

    result = evaluator._evaluate_language(case, simplified_copy)

    assert result["score"] < 70
    assert "这个" in result["details"]["simplified_only_terms"]
    assert "视频" in result["details"]["simplified_only_terms"]


def test_baseline_comparison_detects_dimension_regression(evaluator: ModuleType, dataset: dict):
    report = evaluator.run_evaluation(dataset)
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    assert evaluator.compare_with_baseline(report, baseline)["passed"] is True

    regressed = copy.deepcopy(report)
    regressed["cases"][0]["rules"]["filmability"]["score"] = 60
    comparison = evaluator.compare_with_baseline(regressed, baseline)

    assert comparison["passed"] is False
    assert any(
        item["case_key"] == "zh-cn-tomato-douyin" and item["metric"] == "filmability"
        for item in comparison["regressions"]
    )


def test_cli_writes_report_and_returns_nonzero_for_regression(
    evaluator: ModuleType, tmp_path: Path
):
    output_path = tmp_path / "report.json"
    success = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert success.returncode == 0, success.stderr
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert report["baseline_comparison"]["passed"] is True

    strict_baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    strict_baseline["cases"][0]["overall_score"] = 101
    strict_path = tmp_path / "strict-baseline.json"
    strict_path.write_text(
        json.dumps(strict_baseline, ensure_ascii=False),
        encoding="utf-8",
    )
    failed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--baseline",
            str(strict_path),
            "--output",
            str(tmp_path / "regressed.json"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert failed.returncode != 0
