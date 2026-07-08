from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any


METRICS = ("faithfulness", "answer_relevancy", "answer_correctness")


@dataclass(frozen=True)
class RowComparison:
    index: int
    question: str
    target: bool
    baseline: dict[str, float | None]
    candidate: dict[str, float | None]
    delta: dict[str, float | None]


def load_report(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        report = json.load(f)
    if "rows" not in report or not isinstance(report["rows"], list):
        raise ValueError(f"{path} is not a RAGAS report JSON with a rows list")
    return report


def parse_index_set(raw_values: list[str]) -> set[int]:
    indices: set[int] = set()
    for raw_value in raw_values:
        for part in raw_value.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start, end = part.split("-", maxsplit=1)
                indices.update(range(int(start), int(end) + 1))
            else:
                indices.add(int(part))
    return indices


def is_target_question(question: str, index: int, patterns: list[re.Pattern[str]], indices: set[int]) -> bool:
    return index in indices or any(pattern.search(question) for pattern in patterns)


def row_metric(row: dict[str, Any], metric: str) -> float | None:
    value = row.get(metric)
    if value is None:
        return None
    return float(value)


def compare_rows(
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    *,
    target_patterns: list[str],
    target_indices: set[int],
) -> list[RowComparison]:
    if len(baseline_rows) != len(candidate_rows):
        raise ValueError(
            f"Report row counts differ: baseline={len(baseline_rows)}, candidate={len(candidate_rows)}"
        )

    patterns = [re.compile(pattern, re.I) for pattern in target_patterns]
    comparisons: list[RowComparison] = []
    for offset, (baseline_row, candidate_row) in enumerate(zip(baseline_rows, candidate_rows), start=1):
        baseline_question = str(baseline_row.get("question") or "")
        candidate_question = str(candidate_row.get("question") or "")
        if baseline_question != candidate_question:
            raise ValueError(
                f"Question mismatch at 1-based row {offset}: "
                f"{baseline_question[:80]!r} != {candidate_question[:80]!r}"
            )

        index = int(candidate_row.get("index", offset - 1))
        baseline_metrics = {metric: row_metric(baseline_row, metric) for metric in METRICS}
        candidate_metrics = {metric: row_metric(candidate_row, metric) for metric in METRICS}
        delta_metrics = {
            metric: (
                None
                if baseline_metrics[metric] is None or candidate_metrics[metric] is None
                else candidate_metrics[metric] - baseline_metrics[metric]
            )
            for metric in METRICS
        }
        comparisons.append(
            RowComparison(
                index=index,
                question=candidate_question,
                target=is_target_question(candidate_question, index, patterns, target_indices),
                baseline=baseline_metrics,
                candidate=candidate_metrics,
                delta=delta_metrics,
            )
        )
    return comparisons


def aggregate(rows: list[RowComparison], side: str) -> dict[str, float | None]:
    values: dict[str, float | None] = {}
    for metric in METRICS:
        nums = [
            getattr(row, side)[metric]
            for row in rows
            if getattr(row, side)[metric] is not None
        ]
        values[metric] = mean(nums) if nums else None
    return values


def aggregate_delta(rows: list[RowComparison]) -> dict[str, float | None]:
    values: dict[str, float | None] = {}
    for metric in METRICS:
        nums = [row.delta[metric] for row in rows if row.delta[metric] is not None]
        values[metric] = mean(nums) if nums else None
    return values


def summarize_group(rows: list[RowComparison]) -> dict[str, Any]:
    return {
        "count": len(rows),
        "baseline": aggregate(rows, "baseline"),
        "candidate": aggregate(rows, "candidate"),
        "delta": aggregate_delta(rows),
    }


def format_float(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def markdown_table_for_groups(summary: dict[str, Any]) -> str:
    lines = [
        "| Group | Count | Baseline correctness | Candidate correctness | Correctness delta | Baseline faithfulness | Candidate faithfulness | Faithfulness delta | Baseline relevancy | Candidate relevancy | Relevancy delta |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for group_name in ("all", "target", "non_target"):
        group = summary["groups"][group_name]
        lines.append(
            "| "
            + " | ".join(
                [
                    group_name,
                    str(group["count"]),
                    format_float(group["baseline"]["answer_correctness"]),
                    format_float(group["candidate"]["answer_correctness"]),
                    format_float(group["delta"]["answer_correctness"]),
                    format_float(group["baseline"]["faithfulness"]),
                    format_float(group["candidate"]["faithfulness"]),
                    format_float(group["delta"]["faithfulness"]),
                    format_float(group["baseline"]["answer_relevancy"]),
                    format_float(group["candidate"]["answer_relevancy"]),
                    format_float(group["delta"]["answer_relevancy"]),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def top_changes(rows: list[RowComparison], metric: str, limit: int, reverse: bool) -> list[RowComparison]:
    scored = [row for row in rows if row.delta[metric] is not None]
    return sorted(scored, key=lambda row: row.delta[metric] or 0.0, reverse=reverse)[:limit]


def row_to_dict(row: RowComparison) -> dict[str, Any]:
    return {
        "index": row.index,
        "question": row.question,
        "target": row.target,
        "baseline": row.baseline,
        "candidate": row.candidate,
        "delta": row.delta,
    }


def verdict(
    summary: dict[str, Any],
    *,
    primary_metric: str,
    min_target_delta: float,
    max_non_target_drop: float,
    max_full_drop: float,
) -> dict[str, Any]:
    target_delta = summary["groups"]["target"]["delta"][primary_metric]
    non_target_delta = summary["groups"]["non_target"]["delta"][primary_metric]
    full_delta = summary["groups"]["all"]["delta"][primary_metric]
    target_ok = target_delta is not None and target_delta >= min_target_delta
    non_target_ok = non_target_delta is not None and non_target_delta >= -max_non_target_drop
    full_ok = full_delta is not None and full_delta >= -max_full_drop
    passed = target_ok and non_target_ok and full_ok
    return {
        "primary_metric": primary_metric,
        "passed": passed,
        "target_ok": target_ok,
        "non_target_ok": non_target_ok,
        "full_ok": full_ok,
        "min_target_delta": min_target_delta,
        "max_non_target_drop": max_non_target_drop,
        "max_full_drop": max_full_drop,
    }


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    baseline = load_report(Path(args.baseline))
    candidate = load_report(Path(args.candidate))
    comparisons = compare_rows(
        baseline["rows"],
        candidate["rows"],
        target_patterns=args.target_pattern,
        target_indices=parse_index_set(args.target_index),
    )
    target_rows = [row for row in comparisons if row.target]
    non_target_rows = [row for row in comparisons if not row.target]
    summary = {
        "baseline": str(args.baseline),
        "candidate": str(args.candidate),
        "groups": {
            "all": summarize_group(comparisons),
            "target": summarize_group(target_rows),
            "non_target": summarize_group(non_target_rows),
        },
        "largest_drops": [
            row_to_dict(row)
            for row in top_changes(comparisons, args.primary_metric, args.top_n, reverse=False)
        ],
        "largest_gains": [
            row_to_dict(row)
            for row in top_changes(comparisons, args.primary_metric, args.top_n, reverse=True)
        ],
    }
    summary["verdict"] = verdict(
        summary,
        primary_metric=args.primary_metric,
        min_target_delta=args.min_target_delta,
        max_non_target_drop=args.max_non_target_drop,
        max_full_drop=args.max_full_drop,
    )
    return summary


def write_markdown(summary: dict[str, Any], output: Path) -> None:
    verdict_data = summary["verdict"]
    lines = [
        "# RAGAS Regression Comparison",
        "",
        f"Baseline: `{summary['baseline']}`",
        f"Candidate: `{summary['candidate']}`",
        "",
        f"Verdict: **{'PASS' if verdict_data['passed'] else 'FAIL'}**",
        "",
        markdown_table_for_groups(summary),
        "",
        "## Acceptance Rules",
        "",
        f"- Primary metric: `{verdict_data['primary_metric']}`",
        f"- Target delta must be >= {verdict_data['min_target_delta']:.4f}: `{verdict_data['target_ok']}`",
        f"- Non-target delta must be >= -{verdict_data['max_non_target_drop']:.4f}: `{verdict_data['non_target_ok']}`",
        f"- Full-set delta must be >= -{verdict_data['max_full_drop']:.4f}: `{verdict_data['full_ok']}`",
        "",
        "## Largest Correctness Drops",
        "",
        "| Row | Target | Baseline | Candidate | Delta | Question |",
        "| ---: | --- | ---: | ---: | ---: | --- |",
    ]
    primary_metric = verdict_data["primary_metric"]
    for row in summary["largest_drops"]:
        lines.append(
            f"| {row['index'] + 1} | {row['target']} | "
            f"{format_float(row['baseline'][primary_metric])} | "
            f"{format_float(row['candidate'][primary_metric])} | "
            f"{format_float(row['delta'][primary_metric])} | "
            f"{row['question'].replace('|', '/')} |"
        )
    lines.extend(
        [
            "",
            "## Largest Correctness Gains",
            "",
            "| Row | Target | Baseline | Candidate | Delta | Question |",
            "| ---: | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for row in summary["largest_gains"]:
        lines.append(
            f"| {row['index'] + 1} | {row['target']} | "
            f"{format_float(row['baseline'][primary_metric])} | "
            f"{format_float(row['candidate'][primary_metric])} | "
            f"{format_float(row['delta'][primary_metric])} | "
            f"{row['question'].replace('|', '/')} |"
        )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two RAGAS JSON reports with target/non-target regression gates.")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output", required=True, help="Markdown output path")
    parser.add_argument("--json-output", default=None, help="Optional JSON summary output path")
    parser.add_argument(
        "--target-pattern",
        action="append",
        default=[],
        help="Regex marking target questions. Can be repeated.",
    )
    parser.add_argument(
        "--target-index",
        action="append",
        default=[],
        help="0-based target row index or range, e.g. 3,9,13 or 3-5. Can be repeated.",
    )
    parser.add_argument("--primary-metric", choices=METRICS, default="answer_correctness")
    parser.add_argument("--min-target-delta", type=float, default=0.0)
    parser.add_argument("--max-non-target-drop", type=float, default=0.01)
    parser.add_argument("--max-full-drop", type=float, default=0.0)
    parser.add_argument("--top-n", type=int, default=12)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = build_summary(args)
    write_markdown(summary, Path(args.output))
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary["groups"], indent=2, ensure_ascii=False))
    print(json.dumps(summary["verdict"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
