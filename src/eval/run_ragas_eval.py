from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

from dotenv import load_dotenv
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI
from ragas import EvaluationDataset, SingleTurnSample, evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics._answer_correctness import answer_correctness
from ragas.metrics._answer_relevance import answer_relevancy
from ragas.metrics._context_precision import context_precision
from ragas.metrics._context_recall import context_recall
from ragas.metrics._faithfulness import faithfulness
from ragas.metrics._noise_sensitivity import NoiseSensitivity
from llama_index.core import Settings

from src.eval.retrieval_metrics import aggregate_retrieval_rows, retrieval_metrics_for_hits
from src.eval.run_eval import load_questions, load_replay_planner
from src.retrieval.evidence import EvidenceRetriever
from src.retrieval.evidence_package import (
    EvidenceDecision,
    EvidencePackage,
    aggregate_evidence_packages,
)
from src.retrieval.hybrid import format_hits_as_evidence
from src.settings import init_settings
from src.retrieval.planner import RetrievalPlanner

GENERATION_PROMPT = """You are a financial analyst assistant answering from retrieved evidence.

Rules:
1. Use only the retrieved evidence.
2. Answer the exact question in the first sentence.
3. If the final metric is not stated directly but the required line items are present, do the simple arithmetic and show the formula.
4. Do not answer "insufficient evidence" just because the final ratio or comparison is not explicitly stated.
5. Say "The provided evidence is insufficient" only when the retrieved evidence lacks the relevant company, period, metric, or required numeric inputs.
6. Include [citation:chunk_id] markers for every factual claim and number.
7. Use at most three concise sentences, plus one calculation line when arithmetic is required.
8. If retrieved evidence contains a deterministic calculation aid, treat its answer guidance as highest-priority evidence and make the final answer direct.
9. Do not combine figures from different companies, fiscal years, quarters, or filing types. If the evidence still conflicts after applying the question's period, state the conflict and cite both sources.
10. Do not list background facts, evidence summaries, or alternative figures that are not necessary to answer the question.
11. For "none", "not disclosed", or other absence claims, answer negatively only when an authoritative complete list or an explicit statement supports the absence.
12. Never infer a missing quarterly amount from a full-year total or outlook. If a required input is absent, state that it is missing.
13. State each calculation only once. Recheck the arithmetic before answering, and make the number in the direct answer exactly match the calculation line.
14. A common share or other equity security is not a debt security. If an authoritative complete Section 12(b) list contains only equity securities, answer that no debt securities are listed.
15. When the question explicitly asks whether a margin is useful, first evaluate the business model. For a financial-services business without a conventional cost-of-goods-sold or operating-margin presentation, answer that the traditional margin is not a useful reported performance measure; do not call this insufficient merely because margin inputs are absent.
16. For largest/smallest line-item questions, exclude statement totals and subtotals from the candidates unless the question explicitly asks for a total.

Output format:
Answer:
- direct answer with citations
Calculation:
- include only when arithmetic is required; otherwise omit

Retrieved evidence:
{evidence}

Question: {question}
Answer:"""


def generate_answer(
    question: str,
    evidence: str,
    package: EvidencePackage | None = None,
) -> str:
    if package and package.decision == EvidenceDecision.INSUFFICIENT:
        missing = ", ".join(package.missing_slots) or "required answer evidence"
        return f"The provided evidence is insufficient. Missing evidence: {missing}."
    if package and package.decision == EvidenceDecision.CONFLICT:
        conflicts = "; ".join(package.conflicts) or "unresolved evidence values"
        return (
            "The retrieved evidence contains an unresolved conflict, so no "
            f"unconditional answer can be given. Conflict: {conflicts}."
        )
    prompt = GENERATION_PROMPT.format(evidence=evidence, question=question)
    response = Settings.llm.complete(prompt)
    return str(response).strip()


def evaluate_generation(
    questions: list[dict],
    generation_top_k: int | None = None,
    context_packing: bool = True,
    table_top_k: int = 3,
    ragas_batch_size: int | None = None,
    checkpoint_output: Path | None = None,
    resume_rows: list[dict] | None = None,
    planner: RetrievalPlanner | None = None,
) -> dict:
    previous_top_k = os.environ.get("TOP_K")
    if generation_top_k is not None:
        os.environ["TOP_K"] = str(generation_top_k)

    try:
        evidence_retriever = EvidenceRetriever(planner=planner)

        deepseek_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        deepseek_base = os.getenv("OPENAI_BASE_URL") or "https://api.deepseek.com/v1"
        eval_model = os.getenv("MODEL", "deepseek-chat")

        evaluator_llm = LangchainLLMWrapper(
            ChatOpenAI(
                model=eval_model,
                openai_api_key=deepseek_key,
                openai_api_base=deepseek_base,
                temperature=0,
            ),
            # DeepSeek's OpenAI-compatible API currently only supports n=1.
            # RAGAS may request n>1 internally; bypass_n makes the wrapper send
            # repeated single-completion prompts instead of passing n to the API.
            bypass_n=True,
        )

        embedding_model = os.getenv("EVAL_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
        eval_embeddings = LangchainEmbeddingsWrapper(
            HuggingFaceEmbeddings(
                model_name=embedding_model,
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )
        )

        # Limit concurrency to avoid DeepSeek rate-limiting
        run_config = None
        try:
            from ragas import RunConfig
            max_workers = int(os.getenv("RAGAS_MAX_WORKERS", "4"))
            timeout_val = int(os.getenv("RAGAS_TIMEOUT", "180"))
            run_config = RunConfig(max_workers=max_workers, timeout=timeout_val)
        except ImportError:
            pass

        resume_by_index = {
            int(row["index"]): row
            for row in (resume_rows or [])
            if (
                row.get("generated_answer")
                and row.get("retrieved_contexts") is not None
                and row.get("retrieval_plan")
            )
        }

        samples: list[SingleTurnSample] = []
        sample_row_indices: list[int] = []
        rows: list[dict] = []

        for idx, item in enumerate(questions):
            question = item["question"]
            reference = item.get("reference_answer", "")
            expected_sources = item.get("expected_sources", [])

            resumed_row = resume_by_index.get(idx)
            if resumed_row is not None:
                rows.append(resumed_row)
                if not row_is_scored(resumed_row):
                    samples.append(
                        SingleTurnSample(
                            user_input=question,
                            retrieved_contexts=resumed_row.get("retrieved_contexts", []),
                            response=resumed_row["generated_answer"],
                            reference=reference,
                        )
                    )
                    sample_row_indices.append(len(rows) - 1)
                if (idx + 1) % 5 == 0:
                    print(f"  Reused/generated answers for {idx + 1}/{len(questions)} questions", flush=True)
                continue

            start = time.perf_counter()
            retrieval_result = evidence_retriever.retrieve(
                question,
                table_top_k=table_top_k,
                pack_context=context_packing,
            )
            hits = retrieval_result.hits
            retrieval_ms = int((time.perf_counter() - start) * 1000)

            contexts = [hit.text for hit in hits]
            evidence = format_hits_as_evidence(
                question,
                hits,
                package=retrieval_result.package,
            )
            retrieval_metrics = retrieval_metrics_for_hits(item, hits)

            gen_start = time.perf_counter()
            answer = generate_answer(question, evidence, retrieval_result.package)
            gen_ms = int((time.perf_counter() - gen_start) * 1000)

            samples.append(
                SingleTurnSample(
                    user_input=question,
                    retrieved_contexts=contexts,
                    response=answer,
                    reference=reference,
                )
            )
            sample_row_indices.append(len(rows))

            rows.append(
                {
                    "index": idx,
                    "question": question,
                    "expected_sources": expected_sources,
                    "expected_pages": item.get("expected_pages", []),
                    "reference_answer": reference,
                    "generated_answer": answer,
                    "generation_top_k": generation_top_k,
                    "context_packing": context_packing,
                    "table_top_k": table_top_k,
                    "retrieval_plan": retrieval_result.plan.model_dump(mode="json"),
                    "evidence_package": retrieval_result.package.model_dump(mode="json"),
                    "num_contexts": len(contexts),
                    "retrieved_contexts": contexts,
                    "retrieved_sources": [
                        hit.metadata.get("source_path")
                        or hit.metadata.get("file_path")
                        or hit.metadata.get("file_name")
                        or "unknown"
                        for hit in hits
                    ],
                    "retrieval_metrics": retrieval_metrics,
                    "citation_ids": [hit.citation_id for hit in hits],
                    "retrieval_ms": retrieval_ms,
                    "generation_ms": gen_ms,
                }
            )

            print(f"  Generated answer for {idx + 1}/{len(questions)}", flush=True)
            if (idx + 1) % 5 == 0:
                write_checkpoint(
                    checkpoint_output,
                    rows,
                    total=len(questions),
                    generation_top_k=generation_top_k,
                    context_packing=context_packing,
                    table_top_k=table_top_k,
                    evaluation_ms=0,
                )

        write_checkpoint(
            checkpoint_output,
            rows,
            total=len(questions),
            generation_top_k=generation_top_k,
            context_packing=context_packing,
            table_top_k=table_top_k,
            evaluation_ms=0,
        )

        print(f"  Running RAGAS evaluation on {len(samples)} samples...")
        eval_start = time.perf_counter()
        enabled_metrics = [
            faithfulness,
            answer_relevancy,
            answer_correctness,
            context_precision,
            context_recall,
            NoiseSensitivity(mode="irrelevant"),
        ]
        batch_size = ragas_batch_size or len(samples)
        batch_size = max(batch_size, 1)

        for batch_start in range(0, len(samples), batch_size):
            batch_end = min(batch_start + batch_size, len(samples))
            print(f"  RAGAS batch {batch_start + 1}-{batch_end}/{len(samples)}")
            result = evaluate(
                dataset=EvaluationDataset(samples=samples[batch_start:batch_end]),
                metrics=enabled_metrics,
                llm=evaluator_llm,
                embeddings=eval_embeddings,
                run_config=run_config,
            )
            metrics_df = result.to_pandas()
            faithfulness_scores = metrics_df.get("faithfulness", [])
            relevancy_scores = metrics_df.get("answer_relevancy", [])
            correctness_scores = metrics_df.get("answer_correctness", [])
            context_precision_scores = metrics_df.get("context_precision", [])
            context_recall_scores = metrics_df.get("context_recall", [])
            noise_sensitivity_scores = metric_scores(
                metrics_df,
                "noise_sensitivity",
            )

            for offset, row_index in enumerate(sample_row_indices[batch_start:batch_end]):
                row = rows[row_index]
                row["faithfulness"] = (
                    float(faithfulness_scores.iloc[offset]) if offset < len(faithfulness_scores) else None
                )
                row["answer_relevancy"] = (
                    float(relevancy_scores.iloc[offset]) if offset < len(relevancy_scores) else None
                )
                row["answer_correctness"] = (
                    float(correctness_scores.iloc[offset]) if offset < len(correctness_scores) else None
                )
                row["context_precision"] = (
                    float(context_precision_scores.iloc[offset])
                    if offset < len(context_precision_scores)
                    else None
                )
                row["context_recall"] = (
                    float(context_recall_scores.iloc[offset]) if offset < len(context_recall_scores) else None
                )
                row["noise_sensitivity"] = (
                    float(noise_sensitivity_scores.iloc[offset])
                    if offset < len(noise_sensitivity_scores)
                    else None
                )

            write_checkpoint(
                checkpoint_output,
                rows,
                total=len(questions),
                generation_top_k=generation_top_k,
                context_packing=context_packing,
                table_top_k=table_top_k,
                evaluation_ms=int((time.perf_counter() - eval_start) * 1000),
            )
        eval_ms = int((time.perf_counter() - eval_start) * 1000)

        return aggregate_result(
            rows,
            total=len(questions),
            generation_top_k=generation_top_k,
            context_packing=context_packing,
            table_top_k=table_top_k,
            evaluation_ms=eval_ms,
        )
    finally:
        if generation_top_k is not None:
            if previous_top_k is None:
                os.environ.pop("TOP_K", None)
            else:
                os.environ["TOP_K"] = previous_top_k


def average_metric(rows: list[dict], key: str) -> float | None:
    values = [row.get(key) for row in rows if row.get(key) is not None]
    if not values:
        return None
    return float(sum(values) / len(values))


def metric_scores(metrics_df, metric_name: str):
    exact = metrics_df.get(metric_name)
    if exact is not None:
        return exact
    matching_column = next(
        (
            column
            for column in metrics_df.columns
            if str(column).startswith(f"{metric_name}(")
        ),
        None,
    )
    return metrics_df.get(matching_column, []) if matching_column else []


def row_is_scored(row: dict) -> bool:
    return all(
        row.get(metric) is not None
        for metric in [
            "faithfulness",
            "answer_relevancy",
            "answer_correctness",
            "context_precision",
            "context_recall",
            "noise_sensitivity",
        ]
    )


def write_checkpoint(
    checkpoint_output: Path | None,
    rows: list[dict],
    *,
    total: int,
    generation_top_k: int | None,
    context_packing: bool,
    table_top_k: int,
    evaluation_ms: int,
) -> None:
    if checkpoint_output is None:
        return
    checkpoint_output.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_output.write_text(
        json.dumps(
            aggregate_result(
                rows,
                total=total,
                generation_top_k=generation_top_k,
                context_packing=context_packing,
                table_top_k=table_top_k,
                evaluation_ms=evaluation_ms,
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def aggregate_result(
    rows: list[dict],
    *,
    total: int,
    generation_top_k: int | None,
    context_packing: bool,
    table_top_k: int,
    evaluation_ms: int,
) -> dict:
    retrieval_summary = aggregate_retrieval_rows(rows)
    return {
        "total": total,
        "scored": sum(1 for row in rows if row.get("answer_correctness") is not None),
        "faithfulness": average_metric(rows, "faithfulness"),
        "answer_relevancy": average_metric(rows, "answer_relevancy"),
        "answer_correctness": average_metric(rows, "answer_correctness"),
        "context_precision": average_metric(rows, "context_precision"),
        "context_recall": average_metric(rows, "context_recall"),
        "noise_sensitivity": average_metric(rows, "noise_sensitivity"),
        "retrieval": retrieval_summary,
        "evidence_contract": aggregate_evidence_packages(rows),
        "generation_top_k": generation_top_k,
        "context_packing": context_packing,
        "table_top_k": table_top_k,
        "evaluation_ms": evaluation_ms,
        "rows": rows,
    }


def write_report(result: dict, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# RAGAS Generation Evaluation Report",
        "",
        "## Summary",
        "",
        f"- Total questions: {result['total']}",
        f"- Scored questions: {result.get('scored', result['total'])}",
    ]
    if result["faithfulness"] is not None:
        lines.append(f"- **Faithfulness**: {result['faithfulness']:.3f}")
    if result["answer_relevancy"] is not None:
        lines.append(f"- **Answer Relevancy**: {result['answer_relevancy']:.3f}")
    if result["answer_correctness"] is not None:
        lines.append(f"- **Answer Correctness**: {result['answer_correctness']:.3f}")
    if result["context_precision"] is not None:
        lines.append(f"- **Context Precision**: {result['context_precision']:.3f}")
    if result["context_recall"] is not None:
        lines.append(f"- **Context Recall**: {result['context_recall']:.3f}")
    if result["noise_sensitivity"] is not None:
        lines.append(f"- **Noise Sensitivity (irrelevant)**: {result['noise_sensitivity']:.3f}")
    retrieval_summary = result.get("retrieval", {})
    if retrieval_summary:
        lines.append(f"- Source Hit Rate: {_format_optional_metric(retrieval_summary.get('source_hit_rate'))}")
        lines.append(f"- Source MRR: {_format_optional_metric(retrieval_summary.get('source_mrr'))}")
        lines.append(f"- Page Hit Rate: {_format_optional_metric(retrieval_summary.get('page_hit_rate'))}")
        lines.append(f"- Page MRR: {_format_optional_metric(retrieval_summary.get('page_mrr'))}")
        lines.append(f"- Expected-page Recall: {_format_optional_metric(retrieval_summary.get('expected_page_recall'))}")
        lines.append(
            f"- Lexical reference coverage: {_format_optional_metric(retrieval_summary.get('lexical_reference_coverage'))}"
        )
    evidence_contract = result.get("evidence_contract", {})
    if evidence_contract:
        lines.append(
            f"- Evidence slot completeness: {_format_optional_metric(evidence_contract.get('average_completeness'))}"
        )
        lines.append(
            f"- Fully answered rate: {_format_optional_metric(evidence_contract.get('fully_answered_rate'))}"
        )
        lines.append(
            f"- Evidence decisions: {json.dumps(evidence_contract.get('decision_counts', {}), ensure_ascii=False)}"
        )
    if result.get("generation_top_k") is not None:
        lines.append(f"- Generation top-k: {result['generation_top_k']}")
    lines.append(f"- Structure-aware context packing: {result.get('context_packing', False)}")
    lines.append(f"- Table top-k: {result.get('table_top_k', 0)}")
    lines.append(f"- Evaluation time: {result['evaluation_ms']} ms")
    lines.extend(["", "## Per-question Results", ""])

    for row in result["rows"]:
        lines.extend(
            [
                f"### Q{row['index'] + 1}: {row['question']}",
                "",
            ]
        )
        if row.get("faithfulness") is not None:
            lines.append(f"- Faithfulness: {row['faithfulness']:.3f}")
        if row.get("answer_relevancy") is not None:
            lines.append(f"- Answer Relevancy: {row['answer_relevancy']:.3f}")
        if row.get("answer_correctness") is not None:
            lines.append(f"- Answer Correctness: {row['answer_correctness']:.3f}")
        if row.get("context_precision") is not None:
            lines.append(f"- Context Precision: {row['context_precision']:.3f}")
        if row.get("context_recall") is not None:
            lines.append(f"- Context Recall: {row['context_recall']:.3f}")
        if row.get("noise_sensitivity") is not None:
            lines.append(f"- Noise Sensitivity (irrelevant): {row['noise_sensitivity']:.3f}")
        retrieval_metrics = row.get("retrieval_metrics")
        if retrieval_metrics:
            lines.extend(
                [
                    f"- Source hit: {retrieval_metrics['source_hit']}",
                    f"- Source first rank: {retrieval_metrics['source_first_rank']}",
                    f"- Page hit: {retrieval_metrics['page_hit']}",
                    f"- Page first rank: {retrieval_metrics['page_first_rank']}",
                    f"- Expected-page recall: {_format_optional_metric(retrieval_metrics['expected_page_recall'])}",
                    f"- Lexical reference coverage: {_format_optional_metric(retrieval_metrics['lexical_reference_coverage'])}",
                ]
            )
        lines.extend(
            [
                f"- Retrieval: {row['retrieval_ms']} ms",
                f"- Generation: {row['generation_ms']} ms",
                f"- Contexts: {row['num_contexts']}",
                f"- Citation ids: {', '.join(row.get('citation_ids', []))}",
                f"- Planner intent: {row.get('retrieval_plan', {}).get('intent', 'unknown')}",
                f"- Planner tools: {', '.join(row.get('retrieval_plan', {}).get('tools', []))}",
                f"- Evidence slots: {len(row.get('retrieval_plan', {}).get('evidence_slots', []))}",
                f"- Evidence decision: {row.get('evidence_package', {}).get('decision', 'unknown')}",
                f"- Slot completeness: {_format_optional_metric(row.get('evidence_package', {}).get('completeness'))}",
                f"- Structure-aware context packing: {row.get('context_packing', False)}",
                f"- Table top-k: {row.get('table_top_k', 0)}",
                "",
                "**Generated Answer:**",
                "",
                row["generated_answer"],
                "",
                "**Reference Answer:**",
                "",
                row["reference_answer"],
                "",
                "---",
                "",
            ]
        )
    output.write_text("\n".join(lines), encoding="utf-8")


def _format_optional_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RAGAS generation evaluation.")
    parser.add_argument("--questions", default="eval/questions.jsonl")
    parser.add_argument("--output", default="reports/ragas_eval_report.md")
    parser.add_argument("--json-output", default="reports/ragas_eval_report.json")
    parser.add_argument(
        "--plans-input",
        default=None,
        help="Replay retrieval plans from a retrieval evaluation JSON report.",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Zero-based question offset. Useful for targeted subset evaluation.",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--generation-top-k",
        type=int,
        default=None,
        help="Temporarily override TOP_K for generation evaluation without editing .env.",
    )
    parser.add_argument(
        "--disable-context-packing",
        action="store_true",
        help="Disable structure-aware parent-child context packing.",
    )
    parser.add_argument(
        "--table-top-k",
        type=int,
        default=3,
        help="Add top-k Docling table retrieval results as extra generation evidence.",
    )
    parser.add_argument(
        "--ragas-batch-size",
        type=int,
        default=None,
        help="Run RAGAS scoring in smaller batches for full evaluation stability.",
    )
    parser.add_argument(
        "--checkpoint-output",
        default=None,
        help="Optional JSON checkpoint written after each RAGAS batch.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume generated answers and completed scores from --checkpoint-output when it exists.",
    )
    args = parser.parse_args()

    load_dotenv("src/.env")
    init_settings()

    questions = load_questions(Path(args.questions))
    if args.start:
        questions = questions[args.start :]
    if args.limit is not None:
        questions = questions[: args.limit]
    print(f"Loaded {len(questions)} questions")

    checkpoint_path = Path(args.checkpoint_output) if args.checkpoint_output else None
    resume_rows = None
    if args.resume and checkpoint_path is not None and checkpoint_path.exists():
        checkpoint_data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        resume_rows = checkpoint_data.get("rows", [])
        print(f"Loaded {len(resume_rows)} checkpoint rows from {checkpoint_path}")

    result = evaluate_generation(
        questions,
        generation_top_k=args.generation_top_k,
        context_packing=not args.disable_context_packing,
        table_top_k=args.table_top_k,
        ragas_batch_size=args.ragas_batch_size,
        checkpoint_output=checkpoint_path,
        resume_rows=resume_rows,
        planner=(
            load_replay_planner(Path(args.plans_input))
            if args.plans_input
            else None
        ),
    )

    Path(args.json_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json_output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_report(result, Path(args.output))

    summary = {
        k: result[k]
        for k in [
            "total",
            "faithfulness",
            "answer_relevancy",
            "answer_correctness",
            "context_precision",
            "context_recall",
            "noise_sensitivity",
            "generation_top_k",
            "context_packing",
            "table_top_k",
            "evaluation_ms",
        ]
    }
    summary["retrieval"] = result.get("retrieval", {})
    print(json.dumps(summary, indent=2))
    print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
