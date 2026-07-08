from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def pdf_name_for_doc(doc_name: str) -> str:
    return f"{doc_name}.pdf"


def select_docs(rows: list[dict], pdf_dir: Path, doc_limit: int) -> list[str]:
    counts = Counter(row["doc_name"] for row in rows)
    selected: list[str] = []
    for doc_name, _ in counts.most_common():
        if (pdf_dir / pdf_name_for_doc(doc_name)).exists():
            selected.append(doc_name)
        if len(selected) >= doc_limit:
            break
    return selected


def to_eval_row(row: dict) -> dict:
    doc_name = row["doc_name"]
    evidence_pages = sorted(
        {
            evidence.get("evidence_page_num")
            for evidence in row.get("evidence", [])
            if evidence.get("evidence_page_num") is not None
        }
    )
    return {
        "id": row.get("financebench_id"),
        "dataset": "financebench",
        "company": row.get("company"),
        "question_type": row.get("question_type"),
        "question_reasoning": row.get("question_reasoning"),
        "question": row["question"],
        "expected_sources": [pdf_name_for_doc(doc_name)],
        "expected_doc_name": doc_name,
        "expected_pages": evidence_pages,
        "reference_answer": row.get("answer"),
        "reference_justification": row.get("justification"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare a lightweight FinanceBench subset for local RAG experiments."
    )
    parser.add_argument(
        "--source",
        default="/private/tmp/financebench",
        help="Path to a cloned patronus-ai/financebench repository.",
    )
    parser.add_argument("--doc-limit", type=int, default=5)
    parser.add_argument("--question-limit", type=int, default=20)
    parser.add_argument("--data-dir", default="ui/data/financebench")
    parser.add_argument("--eval-output", default="eval/financebench_questions.jsonl")
    args = parser.parse_args()

    source = Path(args.source)
    data_path = source / "data" / "financebench_open_source.jsonl"
    pdf_dir = source / "pdfs"
    if not data_path.exists() or not pdf_dir.exists():
        raise FileNotFoundError(
            "FinanceBench source is missing data/financebench_open_source.jsonl or pdfs/. "
            "Clone https://github.com/patronus-ai/financebench first."
        )

    rows = read_jsonl(data_path)
    selected_docs = select_docs(rows, pdf_dir, args.doc_limit)
    if not selected_docs:
        raise RuntimeError("No matching FinanceBench PDFs found.")

    output_data_dir = Path(args.data_dir)
    output_data_dir.mkdir(parents=True, exist_ok=True)
    for doc_name in selected_docs:
        src = pdf_dir / pdf_name_for_doc(doc_name)
        dst = output_data_dir / src.name
        shutil.copy2(src, dst)

    selected_doc_set = set(selected_docs)
    selected_questions = [
        to_eval_row(row)
        for row in rows
        if row["doc_name"] in selected_doc_set and (pdf_dir / pdf_name_for_doc(row["doc_name"])).exists()
    ][: args.question_limit]

    eval_output = Path(args.eval_output)
    eval_output.parent.mkdir(parents=True, exist_ok=True)
    eval_output.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in selected_questions) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "dataset": "financebench",
                "documents": selected_docs,
                "document_count": len(selected_docs),
                "question_count": len(selected_questions),
                "data_dir": str(output_data_dir),
                "eval_output": str(eval_output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
