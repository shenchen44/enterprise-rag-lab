from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from src.retrieval.source_period import governance_metadata
from src.vector_store import get_chroma_collection, get_table_chroma_collection


def migrate_collection(collection, *, batch_size: int) -> int:
    data = collection.get(include=["metadatas"])
    ids = data.get("ids") or []
    metadatas = data.get("metadatas") or []
    for start in range(0, len(ids), batch_size):
        batch_ids = ids[start : start + batch_size]
        batch_metadata = [
            {**(metadata or {}), **governance_metadata(metadata or {})}
            for metadata in metadatas[start : start + batch_size]
        ]
        collection.update(ids=batch_ids, metadatas=batch_metadata)
    return len(ids)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add governed tenant, ACL, version, company, and period metadata."
    )
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument(
        "--table-only",
        action="store_true",
        help="Migrate only the table projection.",
    )
    args = parser.parse_args()
    load_dotenv(Path("src") / ".env")

    migrated = {}
    if not args.table_only:
        migrated["chunks"] = migrate_collection(
            get_chroma_collection(),
            batch_size=args.batch_size,
        )
    migrated["table_records"] = migrate_collection(
        get_table_chroma_collection(),
        batch_size=args.batch_size,
    )
    print(json.dumps(migrated, indent=2))


if __name__ == "__main__":
    main()
