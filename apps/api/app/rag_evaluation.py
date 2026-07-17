"""Offline, auditable evaluation for traceable RAG citation retrieval."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.retrieval import (
    KnowledgeChunk,
    RetrievalCandidate,
    hybrid_retrieve,
)

EVALUATOR_VERSION = "rag-citation-evaluator-v1"
REPORT_VERSION = "rag-citation-report-v1"
SUPPORTED_LOCALES = frozenset({"zh-CN", "zh-HK", "en"})
DOCUMENT_LOCATORS = {
    "pdf": "page",
    "pptx": "slide",
    "docx": "paragraph",
}


@dataclass(frozen=True, slots=True)
class LoadedDataset:
    """A parsed dataset together with the exact input hash used for auditing."""

    payload: Mapping[str, Any]
    sha256: str
    path: str


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    """Validated retrieval case independent of databases and paid providers."""

    case_id: str
    locale: str
    document_type: str
    query: str
    relevant_chunk_ids: frozenset[str]
    expected_locator: Mapping[str, object]
    candidates: tuple[RetrievalCandidate, ...]
    query_embedding: tuple[float, ...] | None
    expected_strategy: str | None


def load_dataset(path: Path) -> LoadedDataset:
    """Load one UTF-8 JSON dataset and retain a hash of the exact file bytes."""

    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("evaluation dataset root must be an object")
    return LoadedDataset(
        payload=payload,
        sha256=hashlib.sha256(raw).hexdigest(),
        path=str(path.resolve()),
    )


def evaluate_dataset(
    dataset: Mapping[str, Any],
    *,
    dataset_sha256: str = "",
    dataset_path: str = "",
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate a complete offline dataset and return an auditable JSON payload."""

    dataset_version = _required_string(dataset, "dataset_version", "dataset")
    top_ks = _parse_top_ks(dataset.get("top_ks", [1, 3, 5]))
    cases_value = dataset.get("cases")
    if not _is_sequence(cases_value) or not cases_value:
        raise ValueError("evaluation dataset must contain at least one case")

    cases = tuple(_parse_case(case, index) for index, case in enumerate(cases_value, start=1))
    case_reports = tuple(_evaluate_case(case, top_ks) for case in cases)
    aggregate = _aggregate(case_reports, top_ks)
    coverage = _coverage(case_reports)
    thresholds = _parse_thresholds(dataset.get("thresholds"), top_ks)
    threshold_checks = _threshold_checks(aggregate, thresholds, top_ks)
    strategy_checks = {
        str(case["case_id"]): bool(case["metrics"]["strategy_match"]) for case in case_reports
    }
    required_coverage = {
        "locales": sorted(SUPPORTED_LOCALES),
        "document_types": sorted(DOCUMENT_LOCATORS),
        "locator_types": sorted(DOCUMENT_LOCATORS.values()),
        "strategies": ["lexical-v1-fallback"],
    }
    coverage_checks = {
        name: set(required).issubset(set(coverage[name]))
        for name, required in required_coverage.items()
    }
    timestamp = generated_at or datetime.now(UTC)

    return {
        "report_version": REPORT_VERSION,
        "dataset_version": dataset_version,
        "evaluator_version": EVALUATOR_VERSION,
        "generated_at": timestamp.astimezone(UTC).isoformat(),
        "offline": True,
        "paid_api_calls": 0,
        "dataset": {
            "path": dataset_path,
            "sha256": dataset_sha256,
            "case_count": len(case_reports),
        },
        "configuration": {
            "top_ks": list(top_ks),
            "ranking_engine": "app.retrieval.hybrid_retrieve",
            "locator_match": "expected locator key-value subset on first relevant result",
        },
        "thresholds": thresholds,
        "passed": (
            all(threshold_checks.values())
            and all(coverage_checks.values())
            and all(strategy_checks.values())
        ),
        "checks": {
            "metrics": threshold_checks,
            "coverage": coverage_checks,
            "strategy": strategy_checks,
        },
        "coverage": coverage,
        "aggregate": aggregate,
        "cases": list(case_reports),
    }


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    """Write stable, human-readable JSON suitable for CI evidence retention."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parse_case(value: object, index: int) -> EvaluationCase:
    if not isinstance(value, Mapping):
        raise ValueError(f"case {index} must be an object")
    context = f"case {index}"
    case_id = _required_string(value, "case_id", context)
    locale = _required_string(value, "locale", context)
    if locale not in SUPPORTED_LOCALES:
        raise ValueError(f"{context} has unsupported locale: {locale}")
    document_type = _required_string(value, "document_type", context)
    if document_type not in DOCUMENT_LOCATORS:
        raise ValueError(f"{context} has unsupported document_type: {document_type}")
    query = _required_string(value, "query", context)

    relevant_value = value.get("relevant_chunk_ids")
    if not _is_sequence(relevant_value) or not relevant_value:
        raise ValueError(f"{context} must define relevant_chunk_ids")
    relevant_chunk_ids = frozenset(
        _nonempty_string(item, f"{context} relevant_chunk_ids") for item in relevant_value
    )

    expected_locator = _string_object_mapping(
        value.get("expected_locator"),
        f"{context} expected_locator",
    )
    locator_type = DOCUMENT_LOCATORS[document_type]
    if locator_type not in expected_locator:
        raise ValueError(
            f"{context} expected_locator must include {locator_type!r} for {document_type}"
        )

    candidate_values = value.get("candidates")
    if not _is_sequence(candidate_values) or not candidate_values:
        raise ValueError(f"{context} must contain candidates")
    candidates = tuple(
        _parse_candidate(candidate, case_id, ordinal)
        for ordinal, candidate in enumerate(candidate_values)
    )
    candidate_ids = [candidate.chunk.id for candidate in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError(f"{context} candidate chunk IDs must be unique")
    missing_relevant = relevant_chunk_ids - set(candidate_ids)
    if missing_relevant:
        raise ValueError(
            f"{context} references missing relevant chunks: {sorted(missing_relevant)}"
        )

    query_embedding = _optional_vector(value.get("query_embedding"), context)
    expected_strategy_value = value.get("expected_strategy")
    expected_strategy = (
        _nonempty_string(expected_strategy_value, f"{context} expected_strategy")
        if expected_strategy_value is not None
        else None
    )
    return EvaluationCase(
        case_id=case_id,
        locale=locale,
        document_type=document_type,
        query=query,
        relevant_chunk_ids=relevant_chunk_ids,
        expected_locator=expected_locator,
        candidates=candidates,
        query_embedding=query_embedding,
        expected_strategy=expected_strategy,
    )


def _parse_candidate(
    value: object,
    case_id: str,
    ordinal: int,
) -> RetrievalCandidate:
    if not isinstance(value, Mapping):
        raise ValueError(f"case {case_id} candidate {ordinal + 1} must be an object")
    context = f"case {case_id} candidate {ordinal + 1}"
    chunk_id = _required_string(value, "chunk_id", context)
    text = _required_string(value, "text", context)
    locator = _string_object_mapping(value.get("locator"), f"{context} locator")
    embedding = _optional_vector(value.get("embedding"), context)
    text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    chunk = KnowledgeChunk(
        id=chunk_id,
        organization_id=str(value.get("organization_id") or "offline-eval"),
        source_id=str(value.get("source_id") or f"{case_id}-source"),
        source_group_id=str(value.get("source_group_id") or f"{case_id}-group"),
        revision=_positive_int(value.get("revision", 1), f"{context} revision"),
        ordinal=_nonnegative_int(value.get("ordinal", ordinal), f"{context} ordinal"),
        text=text,
        text_sha256=text_sha256,
        locator=locator,
        title=str(value.get("title") or ""),
    )
    return RetrievalCandidate(chunk=chunk, embedding=embedding)


def _evaluate_case(case: EvaluationCase, top_ks: tuple[int, ...]) -> dict[str, Any]:
    max_k = max(top_ks)
    retrieval = hybrid_retrieve(
        case.query,
        case.candidates,
        query_embedding=case.query_embedding,
        top_k=max_k,
        lexical_limit=max(len(case.candidates), max_k),
        vector_limit=max(len(case.candidates), max_k),
    )
    ranked_ids = [item.candidate.chunk.id for item in retrieval.items]
    first_relevant_rank = next(
        (
            rank
            for rank, chunk_id in enumerate(ranked_ids, start=1)
            if chunk_id in case.relevant_chunk_ids
        ),
        None,
    )
    first_relevant = (
        retrieval.items[first_relevant_rank - 1] if first_relevant_rank is not None else None
    )
    locator_matches = bool(
        first_relevant
        and _locator_matches(
            first_relevant.candidate.chunk.locator,
            case.expected_locator,
        )
    )
    recall = {
        str(k): float(any(chunk_id in case.relevant_chunk_ids for chunk_id in ranked_ids[:k]))
        for k in top_ks
    }
    reciprocal_rank = 1.0 / first_relevant_rank if first_relevant_rank else 0.0
    strategy_matches = (
        case.expected_strategy is None or retrieval.strategy == case.expected_strategy
    )
    return {
        "case_id": case.case_id,
        "locale": case.locale,
        "document_type": case.document_type,
        "locator_type": DOCUMENT_LOCATORS[case.document_type],
        "query": case.query,
        "expected": {
            "relevant_chunk_ids": sorted(case.relevant_chunk_ids),
            "locator": dict(case.expected_locator),
            "strategy": case.expected_strategy,
        },
        "observed": {
            "strategy": retrieval.strategy,
            "fallback_reason": retrieval.fallback_reason,
            "first_relevant_rank": first_relevant_rank,
            "first_relevant_locator": (
                dict(first_relevant.candidate.chunk.locator) if first_relevant is not None else None
            ),
        },
        "metrics": {
            "recall_at_k": recall,
            "reciprocal_rank": round(reciprocal_rank, 8),
            "locator_accuracy": float(locator_matches),
            "strategy_match": strategy_matches,
        },
        "results": [
            {
                "rank": rank,
                "chunk_id": item.candidate.chunk.id,
                "source_id": item.candidate.chunk.source_id,
                "locator": dict(item.candidate.chunk.locator),
                "text_sha256": item.candidate.chunk.text_sha256,
                "lexical_score": round(item.lexical_score, 8),
                "lexical_rank": item.lexical_rank,
                "vector_score": (
                    round(item.vector_score, 8) if item.vector_score is not None else None
                ),
                "vector_rank": item.vector_rank,
                "rrf_score": round(item.rrf_score, 8),
                "relevant": item.candidate.chunk.id in case.relevant_chunk_ids,
            }
            for rank, item in enumerate(retrieval.items, start=1)
        ],
    }


def _aggregate(
    case_reports: Sequence[Mapping[str, Any]],
    top_ks: tuple[int, ...],
) -> dict[str, Any]:
    case_count = len(case_reports)
    recall_at_k = {
        str(k): round(
            sum(float(case["metrics"]["recall_at_k"][str(k)]) for case in case_reports)
            / case_count,
            8,
        )
        for k in top_ks
    }
    mrr = round(
        sum(float(case["metrics"]["reciprocal_rank"]) for case in case_reports) / case_count,
        8,
    )
    locator_accuracy = round(
        sum(float(case["metrics"]["locator_accuracy"]) for case in case_reports) / case_count,
        8,
    )
    return {
        "case_count": case_count,
        "recall_at_k": recall_at_k,
        "mrr": mrr,
        "locator_accuracy": locator_accuracy,
        "strategy_match_rate": round(
            sum(bool(case["metrics"]["strategy_match"]) for case in case_reports) / case_count,
            8,
        ),
        "by_locale": _group_metrics(case_reports, "locale", top_ks),
        "by_document_type": _group_metrics(case_reports, "document_type", top_ks),
    }


def _group_metrics(
    case_reports: Sequence[Mapping[str, Any]],
    field: str,
    top_ks: tuple[int, ...],
) -> dict[str, Any]:
    groups: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for case in case_reports:
        groups[str(case[field])].append(case)
    grouped: dict[str, Any] = {}
    for name, cases in sorted(groups.items()):
        count = len(cases)
        grouped[name] = {
            "case_count": count,
            "recall_at_k": {
                str(k): round(
                    sum(float(case["metrics"]["recall_at_k"][str(k)]) for case in cases) / count,
                    8,
                )
                for k in top_ks
            },
            "mrr": round(
                sum(float(case["metrics"]["reciprocal_rank"]) for case in cases) / count,
                8,
            ),
            "locator_accuracy": round(
                sum(float(case["metrics"]["locator_accuracy"]) for case in cases) / count,
                8,
            ),
        }
    return grouped


def _coverage(case_reports: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    return {
        "locales": sorted({str(case["locale"]) for case in case_reports}),
        "document_types": sorted({str(case["document_type"]) for case in case_reports}),
        "locator_types": sorted({str(case["locator_type"]) for case in case_reports}),
        "strategies": sorted({str(case["observed"]["strategy"]) for case in case_reports}),
        "fallback_reasons": sorted(
            {
                str(case["observed"]["fallback_reason"])
                for case in case_reports
                if case["observed"]["fallback_reason"] is not None
            }
        ),
    }


def _parse_thresholds(
    value: object,
    top_ks: tuple[int, ...],
) -> dict[str, Any]:
    source = value if isinstance(value, Mapping) else {}
    recall_value = source.get("minimum_recall_at_k")
    recall_source = recall_value if isinstance(recall_value, Mapping) else {}
    minimum_recall = {
        str(k): _unit_float(recall_source.get(str(k), 0.0), f"Recall@{k} threshold") for k in top_ks
    }
    return {
        "minimum_recall_at_k": minimum_recall,
        "minimum_mrr": _unit_float(source.get("minimum_mrr", 0.0), "MRR threshold"),
        "minimum_locator_accuracy": _unit_float(
            source.get("minimum_locator_accuracy", 0.0),
            "locator accuracy threshold",
        ),
    }


def _threshold_checks(
    aggregate: Mapping[str, Any],
    thresholds: Mapping[str, Any],
    top_ks: tuple[int, ...],
) -> dict[str, bool]:
    checks = {
        f"recall_at_{k}": (
            float(aggregate["recall_at_k"][str(k)])
            >= float(thresholds["minimum_recall_at_k"][str(k)])
        )
        for k in top_ks
    }
    checks["mrr"] = float(aggregate["mrr"]) >= float(thresholds["minimum_mrr"])
    checks["locator_accuracy"] = float(aggregate["locator_accuracy"]) >= float(
        thresholds["minimum_locator_accuracy"]
    )
    return checks


def _locator_matches(
    actual: Mapping[str, object],
    expected: Mapping[str, object],
) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


def _parse_top_ks(value: object) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or not value:
        raise ValueError("top_ks must be a non-empty array")
    top_ks = tuple(sorted({_positive_int(item, "top_ks item") for item in value}))
    return top_ks


def _optional_vector(value: object, context: str) -> tuple[float, ...] | None:
    if value is None:
        return None
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or not value:
        raise ValueError(f"{context} embedding must be a non-empty numeric array")
    vector: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"{context} embedding must contain only numbers")
        vector.append(float(item))
    return tuple(vector)


def _string_object_mapping(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"{context} must be a non-empty object")
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"{context} keys must be non-empty strings")
        if not isinstance(item, (str, int, float, bool)) and item is not None:
            raise ValueError(f"{context} values must be JSON scalars")
        result[key] = item
    return result


def _required_string(value: Mapping[str, Any], key: str, context: str) -> str:
    return _nonempty_string(value.get(key), f"{context} {key}")


def _nonempty_string(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} must be a non-empty string")
    return value.strip()


def _positive_int(value: object, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{context} must be a positive integer")
    return value


def _nonnegative_int(value: object, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{context} must be a non-negative integer")
    return value


def _unit_float(value: object, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context} must be numeric")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{context} must be between 0 and 1")
    return result


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    )


__all__ = [
    "EVALUATOR_VERSION",
    "LoadedDataset",
    "REPORT_VERSION",
    "evaluate_dataset",
    "load_dataset",
    "write_report",
]
