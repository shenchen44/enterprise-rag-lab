from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from src.ingestion.docling_tables import parse_docling_markdown_tables
from src.settings import init_settings
from src.vector_store import get_table_chroma_collection


def main() -> None:
    parser = argparse.ArgumentParser(description="Add Docling PDF page metadata to the existing table index.")
    parser.add_argument("--markdown-dir", default="data/docling/financebench")
    parser.add_argument("--pdf-dir", default="ui/data/financebench")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    load_dotenv(Path("src") / ".env")
    init_settings()
    tables = parse_docling_markdown_tables(Path(args.markdown_dir), Path(args.pdf_dir))
    page_lookup = {
        (table.source_path, table.table_index): table.page_number
        for table in tables
        if table.page_number is not None
    }

    collection = get_table_chroma_collection()
    records = collection.get(include=["metadatas"])
    updates: list[tuple[str, dict]] = []
    for record_id, metadata in zip(records.get("ids") or [], records.get("metadatas") or []):
        metadata = metadata or {}
        key = (str(metadata.get("source_path") or ""), metadata.get("table_index"))
        page_number = page_lookup.get(key)
        if page_number is None or metadata.get("page_number") == page_number:
            continue
        updates.append(
            (
                record_id,
                {**metadata, "page_number": page_number, "page_label": str(page_number)},
            )
        )

    for start in range(0, len(updates), args.batch_size):
        batch = updates[start : start + args.batch_size]
        collection.update(ids=[record_id for record_id, _metadata in batch], metadatas=[metadata for _record_id, metadata in batch])
        print(f"Updated table metadata {start + len(batch)}/{len(updates)}", flush=True)

    print(f"Updated {len(updates)} records with PDF page metadata.")


if __name__ == "__main__":
    main()
