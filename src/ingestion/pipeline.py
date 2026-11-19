from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from llama_index.core.node_parser import TokenTextSplitter
from llama_index.core.readers import SimpleDirectoryReader
from llama_index.core.schema import BaseNode, Document, TextNode

from src.retrieval.source_period import governance_metadata

MANIFEST_PATH = Path(os.getenv("INGESTION_MANIFEST", "src/storage/ingestion_manifest.json"))
PARENT_CHUNKS_PATH = Path(
    os.getenv("PARENT_CHUNKS_PATH", "src/storage/parent_chunks.json")
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def normalize_source_path(metadata: dict) -> str:
    return str(
        metadata.get("source_path")
        or metadata.get("file_path")
        or metadata.get("filename")
        or metadata.get("file_name")
        or ""
    )


def load_documents(data_dir: str) -> list[Document]:
    reader = SimpleDirectoryReader(data_dir, recursive=True)
    return reader.load_data()


def dedupe_documents(documents: Iterable[Document]) -> list[Document]:
    """Remove exact duplicate document texts while preserving metadata."""
    seen: set[str] = set()
    deduped: list[Document] = []
    for doc in documents:
        content_hash = sha256_text(doc.text)
        if content_hash in seen:
            continue
        seen.add(content_hash)
        source_path = normalize_source_path(doc.metadata)
        doc_id = sha256_text(f"{source_path}:{content_hash}")[:24]
        doc.metadata.update(
            {
                "doc_id": doc_id,
                "source_path": source_path,
                "document_content_hash": content_hash,
                "ingested_at": datetime.now(timezone.utc).isoformat(),
                **governance_metadata(doc.metadata),
            }
        )
        deduped.append(doc)
    return deduped


def build_hierarchical_nodes(
    documents: list[Document],
    *,
    parent_chunk_size: int,
    parent_chunk_overlap: int,
    child_chunk_size: int,
    child_chunk_overlap: int,
) -> tuple[list[dict], list[BaseNode]]:
    """Build searchable child chunks and generation-only parent chunks."""
    if parent_chunk_size <= child_chunk_size:
        raise ValueError("parent_chunk_size must be greater than child_chunk_size")

    parent_splitter = TokenTextSplitter(
        chunk_size=parent_chunk_size,
        chunk_overlap=parent_chunk_overlap,
        include_metadata=False,
    )
    child_splitter = TokenTextSplitter(
        chunk_size=child_chunk_size,
        chunk_overlap=child_chunk_overlap,
        include_metadata=False,
    )
    parent_records: list[dict] = []
    child_nodes: list[BaseNode] = []

    parent_index = 0
    for document in documents:
        source_path = normalize_source_path(document.metadata)
        for parent_text in parent_splitter.split_text(document.text):
            parent_text = parent_text.strip()
            if not parent_text:
                continue
            parent_hash = sha256_text(parent_text)
            parent_id = sha256_text(
                f"{source_path}:parent:{parent_index}:{parent_hash}"
            )[:24]
            parent_metadata = {
                **document.metadata,
                "parent_id": parent_id,
                "parent_chunk_index": parent_index,
                "parent_content_hash": parent_hash,
                "parent_chunk_size": parent_chunk_size,
                "parent_chunk_overlap": parent_chunk_overlap,
                "source_path": source_path,
                "retrieval_granularity": "parent_chunk",
            }
            parent_records.append(
                {
                    "id": parent_id,
                    "text": parent_text,
                    "metadata": parent_metadata,
                }
            )

            for child_text in child_splitter.split_text(parent_text):
                child_text = child_text.strip()
                if not child_text:
                    continue
                child_nodes.append(
                    TextNode(
                        text=child_text,
                        metadata={
                            **document.metadata,
                            "parent_id": parent_id,
                            "parent_chunk_index": parent_index,
                            "source_path": source_path,
                        },
                    )
                )
            parent_index += 1

    for chunk_index, node in enumerate(child_nodes):
        text = node.get_content(metadata_mode="none")
        source_path = normalize_source_path(node.metadata)
        chunk_hash = sha256_text(text)
        chunk_id = sha256_text(f"{source_path}:{chunk_index}:{chunk_hash}")[:24]
        node.id_ = chunk_id
        node.metadata.update(
            {
                "chunk_id": chunk_id,
                "chunk_index": chunk_index,
                "chunk_content_hash": chunk_hash,
                "source_path": source_path,
                "chunk_size": child_chunk_size,
                "chunk_overlap": child_chunk_overlap,
                "parent_type": "parent_chunk",
                "retrieval_granularity": "child_chunk",
            }
        )
    return parent_records, child_nodes


def write_parent_chunks(parent_records: list[dict]) -> None:
    PARENT_CHUNKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PARENT_CHUNKS_PATH.write_text(
        json.dumps(parent_records, ensure_ascii=False),
        encoding="utf-8",
    )


def write_manifest(
    documents: list[Document],
    parent_records: list[dict],
    nodes: list[BaseNode],
) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "documents": [
            {
                "doc_id": doc.metadata.get("doc_id"),
                "source_path": normalize_source_path(doc.metadata),
                "file_name": doc.metadata.get("file_name"),
                "file_type": doc.metadata.get("file_type"),
                "content_hash": doc.metadata.get("document_content_hash"),
            }
            for doc in documents
        ],
        "parent_chunks": [
            {
                "parent_id": record["id"],
                "parent_chunk_index": record["metadata"].get("parent_chunk_index"),
                "source_path": normalize_source_path(record["metadata"]),
                "content_hash": record["metadata"].get("parent_content_hash"),
            }
            for record in parent_records
        ],
        "chunks": [
            {
                "chunk_id": node.metadata.get("chunk_id"),
                "chunk_index": node.metadata.get("chunk_index"),
                "source_path": normalize_source_path(node.metadata),
                "file_name": node.metadata.get("file_name"),
                "content_hash": node.metadata.get("chunk_content_hash"),
            }
            for node in nodes
        ],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def run_ingestion(
    data_dir: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
    parent_chunk_size: int = 1024,
    parent_chunk_overlap: int = 120,
) -> list[BaseNode]:
    documents = dedupe_documents(load_documents(data_dir))
    parent_records, nodes = build_hierarchical_nodes(
        documents,
        parent_chunk_size=parent_chunk_size,
        parent_chunk_overlap=parent_chunk_overlap,
        child_chunk_size=chunk_size,
        child_chunk_overlap=chunk_overlap,
    )
    write_parent_chunks(parent_records)
    write_manifest(documents, parent_records, nodes)
    return nodes
