from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from llama_index.core.node_parser import TokenTextSplitter
from llama_index.core.readers import SimpleDirectoryReader
from llama_index.core.schema import BaseNode, Document


MANIFEST_PATH = Path(os.getenv("INGESTION_MANIFEST", "src/storage/ingestion_manifest.json"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def normalize_source_path(metadata: dict) -> str:
    return str(metadata.get("file_path") or metadata.get("filename") or metadata.get("file_name") or "")


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
            }
        )
        deduped.append(doc)
    return deduped


def build_nodes(documents: list[Document], *, chunk_size: int, chunk_overlap: int) -> list[BaseNode]:
    # TokenTextSplitter avoids runtime NLTK corpus downloads, making local and
    # Docker deployment more reliable than sentence-based splitting.
    splitter = TokenTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    nodes = splitter.get_nodes_from_documents(documents)
    for chunk_index, node in enumerate(nodes):
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
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
            }
        )
    return nodes


def write_manifest(documents: list[Document], nodes: list[BaseNode]) -> None:
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


def run_ingestion(data_dir: str, *, chunk_size: int, chunk_overlap: int) -> list[BaseNode]:
    documents = dedupe_documents(load_documents(data_dir))
    nodes = build_nodes(documents, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    write_manifest(documents, nodes)
    return nodes
