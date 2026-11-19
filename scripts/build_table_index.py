from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from src.ingestion.docling_tables import (
    build_table_index,
    parse_docling_markdown_tables,
)
from src.settings import init_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Chroma table index from Docling Markdown outputs.")
    parser.add_argument("--markdown-dir", default="data/docling/financebench")
    parser.add_argument("--pdf-dir", default="ui/data/financebench")
    parser.add_argument("--no-reset", action="store_true")
    parser.add_argument("--batch-size", type=int, default=128)
    args = parser.parse_args()

    load_dotenv(Path("src") / ".env")
    init_settings()

    tables = parse_docling_markdown_tables(Path(args.markdown_dir), Path(args.pdf_dir))
    result = build_table_index(
        tables,
        reset=not args.no_reset,
        batch_size=args.batch_size,
    )
    result["markdown_dir"] = args.markdown_dir
    result["pdf_dir"] = args.pdf_dir
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
