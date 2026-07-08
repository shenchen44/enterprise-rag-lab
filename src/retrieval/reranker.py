from __future__ import annotations

import os
from typing import Protocol

from src.retrieval.tokenizer import tokenize
from src.retrieval.types import RetrievalHit


class Reranker(Protocol):
    def rerank(self, query: str, hits: list[RetrievalHit], *, top_k: int) -> list[RetrievalHit]:
        ...


class LexicalOverlapReranker:
    """Lightweight reranker for local development.

    It is intentionally simple and inspectable. Later, replace this class with
    BGE/Jina/Cohere cross-encoder reranking while keeping the same interface.
    """

    def rerank(self, query: str, hits: list[RetrievalHit], *, top_k: int) -> list[RetrievalHit]:
        query_tokens = set(tokenize(query))
        if not query_tokens:
            return hits[:top_k]

        rescored: list[RetrievalHit] = []
        for hit in hits:
            text_tokens = set(tokenize(hit.text))
            overlap = len(query_tokens & text_tokens) / max(len(query_tokens), 1)
            source_bonus = 0.05 if hit.source == "hybrid_rrf" else 0.0
            rerank_score = 0.75 * overlap + 0.25 * hit.score + source_bonus
            hit.debug["pre_rerank_score"] = hit.score
            hit.debug["lexical_overlap"] = overlap
            hit.score = rerank_score
            hit.source = "reranked"
            rescored.append(hit)

        rescored.sort(key=lambda item: item.score, reverse=True)
        for rank, hit in enumerate(rescored[:top_k], start=1):
            hit.rank = rank
        return rescored[:top_k]


class BGEReranker:
    """Cross-encoder reranker backed by sentence-transformers.

    The model is loaded lazily so importing retrieval code remains fast. The
    first query downloads/loads the model, while later queries reuse it.
    """

    def __init__(self, model_name: str, *, batch_size: int = 16) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(self, query: str, hits: list[RetrievalHit], *, top_k: int) -> list[RetrievalHit]:
        if not hits:
            return []

        pairs = [(query, hit.text) for hit in hits]
        scores = self.model.predict(pairs, batch_size=self.batch_size, show_progress_bar=False)

        rescored: list[RetrievalHit] = []
        for hit, score in zip(hits, scores):
            hit.debug["pre_rerank_score"] = hit.score
            hit.debug["reranker_model"] = self.model_name
            hit.score = float(score)
            hit.source = "bge_reranked"
            rescored.append(hit)

        rescored.sort(key=lambda item: item.score, reverse=True)
        for rank, hit in enumerate(rescored[:top_k], start=1):
            hit.rank = rank
        return rescored[:top_k]


def build_reranker() -> Reranker:
    provider = os.getenv("RERANKER_PROVIDER", "lexical").lower()
    if provider == "bge":
        return BGEReranker(
            os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-base"),
            batch_size=int(os.getenv("RERANKER_BATCH_SIZE", "16")),
        )
    if provider == "lexical":
        return LexicalOverlapReranker()
    raise RuntimeError(f"Unsupported RERANKER_PROVIDER: {provider}")
