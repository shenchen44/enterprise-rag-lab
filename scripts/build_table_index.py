from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from src.ingestion.docling_tables import (
    build_table_index,
    parse_docling_markdown_tables,
    parse_docling_markdown_text_blocks,
)
from src.settings import init_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Chroma table index from Docling Markdown outputs.")
    parser.add_argument("--markdown-dir", default="data/docling/financebench")
    parser.add_argument("--pdf-dir", default="ui/data/financebench")
    parser.add_argument("--no-reset", action="store_true")
    parser.add_argument(
        "--tables-only",
        action="store_true",
        help="Index whole-table records only. By default, table rows and text blocks are indexed as well.",
    )
    parser.add_argument(
        "--disable-text-blocks",
        action="store_true",
        help="Do not index Docling Markdown text blocks.",
    )
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()

    load_dotenv(Path("src") / ".env")
    init_settings()

    tables = parse_docling_markdown_tables(Path(args.markdown_dir), Path(args.pdf_dir))
    text_blocks = []
    if not args.disable_text_blocks and not args.tables_only:
        text_blocks = parse_docling_markdown_text_blocks(Path(args.markdown_dir), Path(args.pdf_dir))
    result = build_table_index(
        tables,
        text_blocks=text_blocks,
        reset=not args.no_reset,
        batch_size=args.batch_size,
        include_rows=not args.tables_only,
    )
    result["markdown_dir"] = args.markdown_dir
    result["pdf_dir"] = args.pdf_dir
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
