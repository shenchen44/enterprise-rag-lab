from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.ingestion.docling_tables import (
    convert_pdf_with_docling,
    extract_markdown_tables,
    extract_markdown_text_blocks,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse PDFs with Docling and extract Markdown tables.")
    parser.add_argument("--data-dir", default="ui/data/financebench")
    parser.add_argument("--output-dir", default="data/docling/financebench")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--pdf", default=None, help="Optional specific PDF filename or path to parse.")
    parser.add_argument("--skip-existing", action="store_true", help="Skip PDFs that already have Markdown output.")
    parser.add_argument(
        "--max-file-size-mb",
        type=float,
        default=None,
        help="Only parse PDFs smaller than or equal to this size. Useful for fast POCs.",
    )
    parser.add_argument(
        "--largest-first",
        action="store_true",
        help="Parse larger PDFs first. Default is smaller PDFs first for faster iteration.",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    if args.pdf:
        pdf_path = Path(args.pdf)
        pdfs = [pdf_path if pdf_path.is_absolute() else data_dir / pdf_path]
    else:
        pdfs = sorted(data_dir.glob("*.pdf"))
    resolved_pdfs: list[Path] = []
    for pdf_path in pdfs:
        if not pdf_path.is_absolute() and not pdf_path.exists():
            pdf_path = data_dir / pdf_path
        resolved_pdfs.append(pdf_path)
    pdfs = sorted(resolved_pdfs, key=lambda path: path.stat().st_size, reverse=args.largest_first)
    if args.max_file_size_mb is not None:
        max_bytes = args.max_file_size_mb * 1024 * 1024
        pdfs = [pdf_path for pdf_path in pdfs if pdf_path.stat().st_size <= max_bytes]
    if args.limit is not None:
        pdfs = pdfs[: args.limit]

    results: list[dict] = []
    failures: list[dict] = []
    skipped: list[dict] = []
    for pdf_path in pdfs:
        markdown_path = output_dir / f"{pdf_path.stem}.md"
        if args.skip_existing and markdown_path.exists():
            print(f"Skipping existing {markdown_path}", flush=True)
            markdown = markdown_path.read_text(encoding="utf-8")
            tables = extract_markdown_tables(markdown, source_path=str(pdf_path))
            text_blocks = extract_markdown_text_blocks(markdown, source_path=str(pdf_path))
            skipped.append(
                {
                    "pdf_path": str(pdf_path),
                    "markdown_path": str(markdown_path),
                    "table_count": len(tables),
                    "text_block_count": len(text_blocks),
                }
            )
            continue
        print(f"Parsing {pdf_path}", flush=True)
        try:
            result = convert_pdf_with_docling(pdf_path, output_dir)
        except Exception as exc:
            failure = {"pdf_path": str(pdf_path), "error": repr(exc)}
            failures.append(failure)
            print(json.dumps(failure, ensure_ascii=False, indent=2), flush=True)
            continue
        markdown = Path(result["markdown_path"]).read_text(encoding="utf-8")
        tables = extract_markdown_tables(markdown, source_path=str(pdf_path))
        text_blocks = extract_markdown_text_blocks(markdown, source_path=str(pdf_path))
        result["table_count"] = len(tables)
        result["text_block_count"] = len(text_blocks)
        result["file_size_mb"] = round(pdf_path.stat().st_size / 1024 / 1024, 3)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)

    parsed_table_count = sum(item["table_count"] for item in results)
    parsed_text_block_count = sum(item["text_block_count"] for item in results)
    skipped_table_count = sum(item["table_count"] for item in skipped)
    skipped_text_block_count = sum(item["text_block_count"] for item in skipped)
    summary = {
        "parsed_pdfs": len(results),
        "skipped_pdfs": len(skipped),
        "failed_pdfs": len(failures),
        "parsed_tables": parsed_table_count,
        "parsed_text_blocks": parsed_text_block_count,
        "skipped_tables": skipped_table_count,
        "skipped_text_blocks": skipped_text_block_count,
        "total_tables": parsed_table_count + skipped_table_count,
        "total_text_blocks": parsed_text_block_count + skipped_text_block_count,
        "output_dir": str(output_dir),
        "results": results,
        "skipped": skipped,
        "failures": failures,
    }
    summary_path = output_dir / "parse_summary.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
