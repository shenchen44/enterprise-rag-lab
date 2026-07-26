from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from dotenv import load_dotenv

from src.eval.retrieval_metrics import (
    aggregate_retrieval_rows,
    evaluate_chunking,
    retrieval_metrics_for_hits,
)
from src.retrieval.hybrid import HybridRetriever
from src.settings import init_settings


def load_questions(path: Path) -> list[dict]:
    questions: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        questions.append(json.loads(line))
    return questions


def evaluate(questions: list[dict]) -> dict:
    retriever = HybridRetriever()
    rows: list[dict] = []
    latencies_ms: list[int] = []

    for item in questions:
        question = item["question"]
        expected_sources = item.get("expected_sources", [])
        start = time.perf_counter()
        hits = retriever.search(question)
        latency_ms = int((time.perf_counter() - start) * 1000)
        latencies_ms.append(latency_ms)

        retrieval_metrics = retrieval_metrics_for_hits(item, hits)

        rows.append(
            {
                "question": question,
                "expected_sources": expected_sources,
                "expected_pages": item.get("expected_pages", []),
                "hit": retrieval_metrics["source_hit"],
                "first_match_rank": retrieval_metrics["source_first_rank"],
                "retrieval_metrics": retrieval_metrics,
                "latency_ms": latency_ms,
                "top_hits": [
                    {
                        "rank": hit.rank,
                        "score": hit.score,
                        "citation_id": hit.citation_id,
                        "source": hit.metadata.get("source_path")
                        or hit.metadata.get("file_path")
                        or hit.metadata.get("file_name"),
                        "page_numbers": sorted(
                            str(value)
                            for key, value in hit.metadata.items()
                            if key in {"page_number", "page_label", "page", "page_index"}
                            and value is not None
                        ),
                        "retrieval_granularity": hit.metadata.get("retrieval_granularity", "chunk"),
                    }
                    for hit in hits
                ],
            }
        )

    total = len(questions)
    chunking_summary = evaluate_chunking(retriever.records, questions)
    for row, chunking_row in zip(rows, chunking_summary["rows"]):
        row["chunking_metrics"] = chunking_row["chunking_metrics"]

    retrieval_summary = aggregate_retrieval_rows(rows)
    return {
        "total": total,
        "hit_rate": retrieval_summary["source_hit_rate"] or 0.0,
        "mrr": retrieval_summary["source_mrr"] or 0.0,
        "avg_latency_ms": sum(latencies_ms) / total if total else 0.0,
        "retrieval": retrieval_summary,
        "chunking": chunking_summary,
        "rows": rows,
    }


def write_report(result: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# RAG Evaluation Report",
        "",
        f"- Total questions: {result['total']}",
        f"- Source Hit Rate: {_format_optional_metric(result['retrieval']['source_hit_rate'])}",
        f"- Source MRR: {_format_optional_metric(result['retrieval']['source_mrr'])}",
        f"- Page Hit Rate: {_format_optional_metric(result['retrieval']['page_hit_rate'])}",
        f"- Page MRR: {_format_optional_metric(result['retrieval']['page_mrr'])}",
        f"- Expected-page Recall: {_format_optional_metric(result['retrieval']['expected_page_recall'])}",
        f"- Retrieved Reference-term Recall: {_format_optional_metric(result['retrieval']['reference_term_recall'])}",
        f"- Avg latency: {result['avg_latency_ms']:.1f} ms",
        "",
        "## Chunking Integrity",
        "",
        "_This section verifies ingestion completeness and chunk-size stability. It does not claim to measure semantic chunk quality; that requires gold evidence spans._",
        "",
        "**Evidence Preservation:**",
        "",
        f"- Indexed chunks: {result['chunking']['chunk_count']}",
        f"- Source chunk coverage: {_format_optional_metric(result['chunking']['source_chunk_coverage'])}",
        f"- Evidence-page chunk coverage: {_format_optional_metric(result['chunking']['evidence_page_coverage'])}",
        f"- Page metadata coverage: {_format_optional_metric(result['chunking']['page_metadata_coverage'])}",
        "",
        "**Chunk Size Profile:**",
        "",
        f"- Average chunk chars: {_format_optional_metric(result['chunking']['avg_chunk_chars'])}",
        f"- Median chunk chars: {_format_optional_metric(result['chunking']['median_chunk_chars'])}",
        f"- P90 chunk chars: {_format_optional_metric(result['chunking']['p90_chunk_chars'])}",
        f"- Empty chunk ratio: {_format_optional_metric(result['chunking']['empty_chunk_ratio'])}",
        "",
        "## Per-question Results",
        "",
    ]
    for row in result["rows"]:
        metrics = row["retrieval_metrics"]
        chunking_metrics = row.get("chunking_metrics", {})
        lines.extend(
            [
                f"### {row['question']}",
                "",
                "**Retrieval:**",
                "",
                f"- Source hit: {metrics['source_hit']}",
                f"- Source first rank: {metrics['source_first_rank']}",
                f"- Page hit: {metrics['page_hit']}",
                f"- Page first rank: {metrics['page_first_rank']}",
                f"- Expected-page recall: {_format_optional_metric(metrics['expected_page_recall'])}",
                f"- Retrieved reference-term recall: {_format_optional_metric(metrics['reference_term_recall'])}",
                f"- Matched reference terms: {', '.join(metrics['matched_reference_terms'][:12])}",
                f"- Latency: {row['latency_ms']} ms",
                "",
                "**Ingestion Integrity:**",
                "",
                f"- Source chunks: {chunking_metrics.get('source_chunk_count')}",
                f"- Evidence chunks: {chunking_metrics.get('evidence_chunk_count')}",
                f"- Evidence-page coverage: {_format_optional_metric(chunking_metrics.get('expected_page_coverage'))}",
                "",
                "- Top hits:",
            ]
        )
        for hit in row["top_hits"]:
            lines.append(
                f"  - rank={hit['rank']} score={hit['score']:.4f} "
                f"citation={hit['citation_id']} source={hit['source']} "
                f"pages={','.join(hit['page_numbers']) or '-'} "
                f"granularity={hit['retrieval_granularity']}"
            )
        lines.append("")
    output.write_text("\n".join(lines), encoding="utf-8")


def _format_optional_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run retrieval evaluation.")
    parser.add_argument("--questions", default="eval/questions.jsonl")
    parser.add_argument("--output", default="reports/rag_eval_report.md")
    parser.add_argument("--json-output", default="reports/rag_eval_report.json")
    args = parser.parse_args()

    load_dotenv("src/.env")
    init_settings()
    result = evaluate(load_questions(Path(args.questions)))
    Path(args.json_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json_output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_report(result, Path(args.output))
    print(
        json.dumps(
            {
                "total": result["total"],
                "retrieval": result["retrieval"],
                "chunking": {
                    key: value
                    for key, value in result["chunking"].items()
                    if key != "rows"
                },
                "avg_latency_ms": result["avg_latency_ms"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
