from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from dotenv import load_dotenv

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


def source_matches(hit_metadata: dict, expected_sources: list[str]) -> bool:
    source = str(
        hit_metadata.get("source_path")
        or hit_metadata.get("file_path")
        or hit_metadata.get("file_name")
        or ""
    )
    return any(expected in source for expected in expected_sources)


def evaluate(questions: list[dict]) -> dict:
    retriever = HybridRetriever()
    rows: list[dict] = []
    hit_count = 0
    reciprocal_ranks: list[float] = []
    latencies_ms: list[int] = []

    for item in questions:
        question = item["question"]
        expected_sources = item.get("expected_sources", [])
        start = time.perf_counter()
        hits = retriever.search(question)
        latency_ms = int((time.perf_counter() - start) * 1000)
        latencies_ms.append(latency_ms)

        first_match_rank = None
        for rank, hit in enumerate(hits, start=1):
            if source_matches(hit.metadata, expected_sources):
                first_match_rank = rank
                break

        hit = first_match_rank is not None
        if hit:
            hit_count += 1
            reciprocal_ranks.append(1.0 / first_match_rank)
        else:
            reciprocal_ranks.append(0.0)

        rows.append(
            {
                "question": question,
                "expected_sources": expected_sources,
                "hit": hit,
                "first_match_rank": first_match_rank,
                "latency_ms": latency_ms,
                "top_hits": [
                    {
                        "rank": hit.rank,
                        "score": hit.score,
                        "citation_id": hit.citation_id,
                        "source": hit.metadata.get("source_path")
                        or hit.metadata.get("file_path")
                        or hit.metadata.get("file_name"),
                    }
                    for hit in hits
                ],
            }
        )

    total = len(questions)
    return {
        "total": total,
        "hit_rate": hit_count / total if total else 0.0,
        "mrr": sum(reciprocal_ranks) / total if total else 0.0,
        "avg_latency_ms": sum(latencies_ms) / total if total else 0.0,
        "rows": rows,
    }


def write_report(result: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# RAG Evaluation Report",
        "",
        f"- Total questions: {result['total']}",
        f"- Hit Rate: {result['hit_rate']:.3f}",
        f"- MRR: {result['mrr']:.3f}",
        f"- Avg latency: {result['avg_latency_ms']:.1f} ms",
        "",
        "## Per-question Results",
        "",
    ]
    for row in result["rows"]:
        lines.extend(
            [
                f"### {row['question']}",
                "",
                f"- Hit: {row['hit']}",
                f"- First match rank: {row['first_match_rank']}",
                f"- Latency: {row['latency_ms']} ms",
                "- Top hits:",
            ]
        )
        for hit in row["top_hits"]:
            lines.append(
                f"  - rank={hit['rank']} score={hit['score']:.4f} "
                f"citation={hit['citation_id']} source={hit['source']}"
            )
        lines.append("")
    output.write_text("\n".join(lines), encoding="utf-8")


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
    print(json.dumps({k: result[k] for k in ["total", "hit_rate", "mrr", "avg_latency_ms"]}, indent=2))


if __name__ == "__main__":
    main()

