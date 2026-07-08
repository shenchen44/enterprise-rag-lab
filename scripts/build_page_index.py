from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from src.ingestion.page_index import build_page_index
from src.settings import init_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a page-level Chroma index for PDF retrieval.")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--no-reset", action="store_true")
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()

    load_dotenv(Path("src") / ".env")
    init_settings()

    data_dir = args.data_dir or os.getenv("DATA_DIR", "ui/data")
    result = build_page_index(
        data_dir,
        reset=not args.no_reset,
        batch_size=args.batch_size,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
