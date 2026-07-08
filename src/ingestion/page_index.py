from __future__ import annotations

import hashlib
from pathlib import Path

from llama_index.core import Settings
from pypdf import PdfReader

from src.vector_store import get_page_chroma_collection


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_page_text(text: str, *, max_chars: int) -> str:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text

    head = text[: max_chars // 2]
    tail = text[-max_chars // 2 :]
    return f"{head}\n...\n{tail}"


def iter_pdf_pages(data_dir: str) -> list[dict]:
    pages: list[dict] = []
    for pdf_path in sorted(Path(data_dir).rglob("*.pdf")):
        reader = PdfReader(str(pdf_path))
        for page_index, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            normalized_text = normalize_page_text(text, max_chars=6000)
            page_number = page_index + 1
            page_id = sha256_text(f"{pdf_path}:{page_number}:{sha256_text(normalized_text)}")[:24]
            pages.append(
                {
                    "id": page_id,
                    "text": normalized_text,
                    "metadata": {
                        "page_id": page_id,
                        "source_path": str(pdf_path),
                        "file_name": pdf_path.name,
                        "file_type": "application/pdf",
                        "page_number": page_number,
                        "page_label": str(page_number),
                        "content_hash": sha256_text(normalized_text),
                        "original_chars": len(text),
                        "indexed_chars": len(normalized_text),
                        "retrieval_granularity": "page",
                    },
                }
            )
    return pages


def build_page_index(data_dir: str, *, reset: bool = True, batch_size: int = 8) -> dict:
    collection = get_page_chroma_collection(reset=reset)
    pages = iter_pdf_pages(data_dir)
    print(f"Extracted {len(pages)} PDF pages from {data_dir}", flush=True)

    for start in range(0, len(pages), batch_size):
        batch = pages[start : start + batch_size]
        texts = [item["text"] for item in batch]
        embeddings = Settings.embed_model.get_text_embedding_batch(texts)
        collection.add(
            ids=[item["id"] for item in batch],
            documents=texts,
            metadatas=[item["metadata"] for item in batch],
            embeddings=embeddings,
        )
        print(f"Indexed pages {start + len(batch)}/{len(pages)}", flush=True)

    return {
        "data_dir": data_dir,
        "page_count": len(pages),
        "collection_count": collection.count(),
    }
