from __future__ import annotations

from llama_index.core import Settings

from src.retrieval.types import RetrievalHit
from src.vector_store import get_page_chroma_collection


class PageRetriever:
    """Vector retriever over full PDF pages.

    This complements chunk-level retrieval for table-heavy financial QA where
    a line item, year header, and nearby values may be split across chunks.
    """

    def __init__(self) -> None:
        self.collection = get_page_chroma_collection()

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
