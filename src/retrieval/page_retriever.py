from __future__ import annotations

import os

from llama_index.core import Settings

from src.retrieval.bm25 import BM25Retriever
from src.retrieval.fusion import reciprocal_rank_fusion
from src.retrieval.types import RetrievalHit
from src.vector_store import get_page_chroma_collection


class PageRetriever:
    """Vector retriever over full PDF pages.

    This complements chunk-level retrieval for table-heavy financial QA where
    a line item, year header, and nearby values may be split across chunks.
    """

    def __init__(self) -> None:
        self.collection = get_page_chroma_collection()
        data = self.collection.get(include=["documents", "metadatas"])
        self.records = [
            {"id": node_id, "text": text or "", "metadata": metadata or {}}
            for node_id, text, metadata in zip(
                data.get("ids") or [],
                data.get("documents") or [],
                data.get("metadatas") or [],
            )
        ]
        self.bm25 = BM25Retriever(self.records)

    def vector_search(self, query: str, *, top_k: int) -> list[RetrievalHit]:
        if top_k <= 0 or self.collection.count() == 0:
            return []

        query_embedding = Settings.embed_model.get_query_embedding(query)
        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        hits: list[RetrievalHit] = []
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        for rank, (node_id, text, metadata, distance) in enumerate(
            zip(ids, documents, metadatas, distances),
            start=1,
        ):
            metadata = metadata or {}
            metadata.setdefault("chunk_id", metadata.get("page_id") or node_id)
            hits.append(
                RetrievalHit(
                    node_id=node_id,
                    text=text or "",
                    metadata=metadata,
                    score=1.0 / (1.0 + float(distance or 0.0)),
                    source="page_vector",
                    rank=rank,
                    debug={"distance": distance, "retrieval_granularity": "page"},
                )
            )
        return hits

    def search(self, query: str, *, top_k: int) -> list[RetrievalHit]:
        vector_hits = self.vector_search(query, top_k=top_k)
        if os.getenv("PAGE_BM25_ENABLED", "true").lower() != "true":
            return vector_hits

        bm25_hits = self.bm25.search(query, top_k=max(top_k * 2, top_k))
        return reciprocal_rank_fusion(
            [vector_hits, bm25_hits],
            top_k=top_k,
            rrf_k=int(os.getenv("RRF_K", "60")),
        )
