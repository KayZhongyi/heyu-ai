#!/usr/bin/env python3
"""Run the dependency-free Heyu AI RAG citation evaluation dataset."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.rag_evaluation import evaluate_dataset, load_dataset, write_report  # noqa: E402

DEFAULT_DATASET = ROOT / "evals" / "rag-citations" / "dataset-v1.json"
DEFAULT_OUTPUT = ROOT / "outputs" / "rag-citation-evaluation.json"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate traceable RAG retrieval and citation locators without "
            "databases, model downloads, or paid APIs."
        )
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    loaded = load_dataset(args.dataset)
    report = evaluate_dataset(
        loaded.payload,
        dataset_sha256=loaded.sha256,
        dataset_path=loaded.path,
    )
    write_report(args.output, report)
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "case_count": report["aggregate"]["case_count"],
                "recall_at_k": report["aggregate"]["recall_at_k"],
                "mrr": report["aggregate"]["mrr"],
                "locator_accuracy": report["aggregate"]["locator_accuracy"],
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
