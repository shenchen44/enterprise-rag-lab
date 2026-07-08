import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.compare_ragas_runs import build_summary, compare_rows, parse_index_set


def report(rows):
    return {"rows": rows}


def row(index: int, question: str, correctness: float, faithfulness: float = 1.0, relevancy: float = 1.0):
    return {
        "index": index,
        "question": question,
        "faithfulness": faithfulness,
        "answer_relevancy": relevancy,
        "answer_correctness": correctness,
    }


def write_report(path: Path, rows) -> None:
    path.write_text(json.dumps(report(rows)), encoding="utf-8")


def test_compare_rows_marks_target_by_pattern_and_index() -> None:
    baseline_rows = [
        row(0, "Does 3M have a quick ratio problem?", 0.3),
        row(1, "What are AMEX geographies?", 0.9),
        row(2, "What drove revenue?", 0.5),
    ]
    candidate_rows = [
        row(0, "Does 3M have a quick ratio problem?", 0.7),
        row(1, "What are AMEX geographies?", 0.2),
        row(2, "What drove revenue?", 0.6),
    ]

    comparisons = compare_rows(
        baseline_rows,
        candidate_rows,
        target_patterns=[r"quick ratio"],
        target_indices={2},
    )

    assert [comparison.target for comparison in comparisons] == [True, False, True]
    assert comparisons[0].delta["answer_correctness"] == 0.39999999999999997
    assert comparisons[1].delta["answer_correctness"] == -0.7


def test_regression_verdict_fails_when_non_target_drops(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    write_report(
        baseline_path,
        [
            row(0, "Quick ratio question", 0.3),
            row(1, "Non target question", 0.9),
        ],
    )
    write_report(
        candidate_path,
        [
            row(0, "Quick ratio question", 0.8),
            row(1, "Non target question", 0.5),
        ],
    )

    args = argparse.Namespace(
        baseline=str(baseline_path),
        candidate=str(candidate_path),
        target_pattern=[r"quick ratio"],
        target_index=[],
        primary_metric="answer_correctness",
        min_target_delta=0.0,
        max_non_target_drop=0.01,
        max_full_drop=0.0,
        top_n=3,
    )
    summary = build_summary(args)

    assert summary["groups"]["target"]["delta"]["answer_correctness"] == 0.5
    assert summary["groups"]["non_target"]["delta"]["answer_correctness"] == -0.4
    assert summary["verdict"]["passed"] is False
    assert summary["verdict"]["target_ok"] is True
    assert summary["verdict"]["non_target_ok"] is False


def test_parse_index_set_supports_ranges() -> None:
    assert parse_index_set(["3,9", "13-15"]) == {3, 9, 13, 14, 15}
