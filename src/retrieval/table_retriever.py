from __future__ import annotations

from llama_index.core import Settings

from src.retrieval.types import RetrievalHit
from src.vector_store import get_table_chroma_collection


class TableRetriever:
    """Vector retriever over Docling-extracted Markdown tables."""

    def __init__(self) -> None:
        self.collection = get_table_chroma_collection()

    def search(self, query: str, *, top_k: int) -> list[RetrievalHit]:
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
