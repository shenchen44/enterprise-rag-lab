from __future__ import annotations

from llama_index.core import Settings

from src.retrieval.bm25 import BM25Retriever
from src.retrieval.fusion import reciprocal_rank_fusion
from src.retrieval.request_context import RetrievalFilter
from src.retrieval.types import RetrievalHit
from src.vector_store import get_table_chroma_collection


class TableRetriever:
    """Hybrid retriever over table rows; complete tables remain generation parents."""

    def __init__(self) -> None:
        self.collection = get_table_chroma_collection()
        data = self.collection.get(include=["documents", "metadatas"])
        self.records = [
            {"id": node_id, "text": text or "", "metadata": metadata or {}}
            for node_id, text, metadata in zip(
                data.get("ids") or [],
                data.get("documents") or [],
                data.get("metadatas") or [],
            )
        ]
        self._tables_by_id = {
            str(record["metadata"].get("table_id")): record
            for record in self.records
            if record["metadata"].get("retrieval_granularity") == "table"
            and record["metadata"].get("table_id")
        }
        self.bm25 = BM25Retriever(self.records)

    def parent_table(self, table_id: str | None) -> dict | None:
        """Return the full table record for a retrieved table row."""
        return self._tables_by_id.get(str(table_id)) if table_id else None

    def search(self, query: str, *, top_k: int) -> list[RetrievalHit]:
        return self._search(query, top_k=top_k)

    def search_rows(
        self,
        query: str,
        *,
        top_k: int,
        retrieval_filter: RetrievalFilter | None = None,
    ) -> list[RetrievalHit]:
        """Retrieve short table rows; parent tables are fetched only after reranking."""
        candidate_k = max(top_k * 2, top_k)
        vector_hits = self._search(
            query,
            top_k=candidate_k,
            where=(
                retrieval_filter.chroma_where(granularity="table_row")
                if retrieval_filter
                else {"retrieval_granularity": "table_row"}
            ),
        )
        bm25_hits = self.bm25.search(
            query,
            top_k=candidate_k,
            retrieval_filter=retrieval_filter,
            granularity="table_row",
        )
        if (
            not vector_hits
            and not bm25_hits
            and retrieval_filter
            and retrieval_filter.has_relaxable_scope
        ):
            relaxed = retrieval_filter.without_period_and_document_type()
            vector_hits = self._search(
                query,
                top_k=candidate_k,
                where=relaxed.chroma_where(granularity="table_row"),
            )
            bm25_hits = self.bm25.search(
                query,
                top_k=candidate_k,
                retrieval_filter=relaxed,
                granularity="table_row",
            )
            for hit in [*vector_hits, *bm25_hits]:
                hit.debug["scope_relaxed"] = [
                    "fiscal_years",
                    "quarter",
                    "document_types",
                ]
        return reciprocal_rank_fusion(
            [
                vector_hits,
                bm25_hits,
            ],
            top_k=top_k,
        )

    def _search(
        self,
        query: str,
        *,
        top_k: int,
        where: dict | None = None,
    ) -> list[RetrievalHit]:
        if top_k <= 0 or self.collection.count() == 0:
            return []

        query_embedding = Settings.embed_model.get_query_embedding(query)
        query_args = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where is not None:
            query_args["where"] = where
        result = self.collection.query(
            **query_args,
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
            metadata.setdefault(
                "chunk_id",
                metadata.get("row_id") or metadata.get("block_id") or metadata.get("table_id") or node_id,
            )
            granularity = metadata.get("retrieval_granularity", "table")
            hits.append(
                RetrievalHit(
                    node_id=node_id,
                    text=text or "",
                    metadata=metadata,
                    score=1.0 / (1.0 + float(distance or 0.0)),
                    source=f"{granularity}_vector",
                    rank=rank,
                    debug={"distance": distance, "retrieval_granularity": granularity},
                )
            )
        return hits
