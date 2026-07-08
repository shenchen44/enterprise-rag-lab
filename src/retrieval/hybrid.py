from __future__ import annotations

import os

from llama_index.core import Settings

from src.retrieval.bm25 import BM25Retriever
from src.retrieval.fusion import reciprocal_rank_fusion
from src.retrieval.reranker import build_reranker
from src.retrieval.types import RetrievalHit
from src.vector_store import get_chroma_collection


def load_chroma_records() -> list[dict]:
    collection = get_chroma_collection()
    data = collection.get(include=["documents", "metadatas"])
    records: list[dict] = []
    for node_id, text, metadata in zip(
        data.get("ids") or [],
        data.get("documents") or [],
        data.get("metadatas") or [],
    ):
        records.append({"id": node_id, "text": text or "", "metadata": metadata or {}})
    return records


class HybridRetriever:
    def __init__(self) -> None:
        self.collection = get_chroma_collection()
        self.records = load_chroma_records()
        self.bm25 = BM25Retriever(self.records)
        self.reranker = build_reranker()

    def vector_search(self, query: str, *, top_k: int) -> list[RetrievalHit]:
        if self.collection.count() == 0:
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
            hits.append(
                RetrievalHit(
                    node_id=node_id,
                    text=text or "",
                    metadata=metadata or {},
                    score=1.0 / (1.0 + float(distance or 0.0)),
                    source="vector",
                    rank=rank,
                    debug={"distance": distance},
                )
            )
        return hits

    def search(self, query: str) -> list[RetrievalHit]:
        vector_top_k = int(os.getenv("VECTOR_TOP_K", "20"))
        bm25_top_k = int(os.getenv("BM25_TOP_K", "20"))
        hybrid_top_k = int(os.getenv("HYBRID_TOP_K", "12"))
        final_top_k = int(os.getenv("TOP_K", "5"))
        rrf_k = int(os.getenv("RRF_K", "60"))
        reranker_enabled = os.getenv("RERANKER_ENABLED", "true").lower() == "true"

        vector_hits = self.vector_search(query, top_k=vector_top_k)
        bm25_hits = self.bm25.search(query, top_k=bm25_top_k)
        fused = reciprocal_rank_fusion(
            [vector_hits, bm25_hits],
            top_k=hybrid_top_k,
            rrf_k=rrf_k,
        )
        if reranker_enabled:
            return self.reranker.rerank(query, fused, top_k=final_top_k)
        return fused[:final_top_k]


def format_hits_as_evidence(query: str, hits: list[RetrievalHit]) -> str:
    if not hits:
        return (
            "No relevant context was found in the knowledge base. "
            "Answer that the knowledge base does not contain enough evidence."
        )

    lines = [
        "Retrieved evidence from the enterprise knowledge base.",
        f"Query: {query}",
        "Use the citation ids exactly as shown when answering.",
        "",
    ]
    for hit in hits:
        metadata = hit.metadata
        source_path = metadata.get("source_path") or metadata.get("file_path") or metadata.get("file_name") or "unknown"
        chunk_index = metadata.get("chunk_index", "")
        lines.append(
            f"[citation:{hit.citation_id}] "
            f"rank={hit.rank} score={hit.score:.4f} source={source_path} chunk={chunk_index}"
        )
        lines.append(hit.text.strip())
        lines.append("")
    return "\n".join(lines)
