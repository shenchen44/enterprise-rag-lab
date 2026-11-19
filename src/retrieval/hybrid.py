from __future__ import annotations

import os
import json
from pathlib import Path

from llama_index.core import Settings

from src.retrieval.bm25 import BM25Retriever
from src.retrieval.fusion import reciprocal_rank_fusion
from src.retrieval.reranker import build_reranker
from src.retrieval.request_context import RetrievalFilter
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


def load_parent_records() -> list[dict]:
    path = Path(os.getenv("PARENT_CHUNKS_PATH", "src/storage/parent_chunks.json"))
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else []


class HybridRetriever:
    def __init__(self) -> None:
        self.collection = get_chroma_collection()
        self.records = load_chroma_records()
        self.parent_records = load_parent_records()
        self.parents_by_id = {
            str(record["id"]): record
            for record in self.parent_records
            if record.get("id")
        }
        self.bm25 = BM25Retriever(self.records)
        self.reranker = build_reranker()

    def vector_search(
        self,
        query: str,
        *,
        top_k: int,
        retrieval_filter: RetrievalFilter | None = None,
    ) -> list[RetrievalHit]:
        if self.collection.count() == 0:
            return []
        query_embedding = Settings.embed_model.get_query_embedding(query)
        query_args = dict(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        if retrieval_filter:
            query_args["where"] = retrieval_filter.chroma_where()
        result = self.collection.query(**query_args)
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
        return self.search_many([query], rerank_query=query)

    def search_many(
        self,
        queries: list[str],
        *,
        rerank_query: str,
        retrieval_filter: RetrievalFilter | None = None,
    ) -> list[RetrievalHit]:
        vector_top_k = int(os.getenv("VECTOR_TOP_K", "20"))
        bm25_top_k = int(os.getenv("BM25_TOP_K", "20"))
        hybrid_top_k = int(os.getenv("HYBRID_TOP_K", "12"))
        final_top_k = int(os.getenv("TOP_K", "5"))
        rrf_k = int(os.getenv("RRF_K", "60"))
        reranker_enabled = os.getenv("RERANKER_ENABLED", "true").lower() == "true"
        clean_queries = list(dict.fromkeys(query.strip() for query in queries if query.strip()))
        candidates: dict[str, RetrievalHit] = {}
        for query in clean_queries:
            vector_hits = self.vector_search(
                query,
                top_k=vector_top_k,
                retrieval_filter=retrieval_filter,
            )
            bm25_hits = self.bm25.search(
                query,
                top_k=bm25_top_k,
                retrieval_filter=retrieval_filter,
            )
            if (
                not vector_hits
                and not bm25_hits
                and retrieval_filter
                and retrieval_filter.has_relaxable_scope
            ):
                relaxed = retrieval_filter.without_period_and_document_type()
                vector_hits = self.vector_search(
                    query,
                    top_k=vector_top_k,
                    retrieval_filter=relaxed,
                )
                bm25_hits = self.bm25.search(
                    query,
                    top_k=bm25_top_k,
                    retrieval_filter=relaxed,
                )
                for hit in [*vector_hits, *bm25_hits]:
                    hit.debug["scope_relaxed"] = [
                        "fiscal_years",
                        "quarter",
                        "document_types",
                    ]
            query_hits = reciprocal_rank_fusion(
                [
                    vector_hits,
                    bm25_hits,
                ],
                top_k=hybrid_top_k,
                rrf_k=rrf_k,
            )
            for hit in query_hits:
                existing = candidates.get(hit.node_id)
                if existing is None or hit.score > existing.score:
                    candidates[hit.node_id] = hit
        fused = sorted(
            candidates.values(),
            key=lambda hit: hit.score,
            reverse=True,
        )

        return (
            self.reranker.rerank(rerank_query, fused, top_k=final_top_k)
            if reranker_enabled
            else fused[:final_top_k]
        )


def format_hits_as_evidence(
    query: str,
    hits: list[RetrievalHit],
    *,
    package=None,
) -> str:
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
    if package is not None:
        lines.extend(
            [
                "Evidence contract:",
                f"- decision: {package.decision.value}",
                f"- completeness: {package.completeness:.3f}",
                f"- missing slots: {', '.join(package.missing_slots) or 'none'}",
                f"- conflicts: {'; '.join(package.conflicts) or 'none'}",
                "",
            ]
        )
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
