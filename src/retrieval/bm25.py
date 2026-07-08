from __future__ import annotations

import math
from collections import Counter

from src.retrieval.tokenizer import tokenize
from src.retrieval.types import RetrievalHit


class BM25Retriever:
    """Small in-project BM25 retriever for learning hybrid search internals."""

    def __init__(self, records: list[dict], *, k1: float = 1.5, b: float = 0.75) -> None:
        self.records = records
        self.k1 = k1
        self.b = b
        self.tokenized = [tokenize(record["text"]) for record in records]
        self.doc_lens = [len(tokens) for tokens in self.tokenized]
        self.avgdl = sum(self.doc_lens) / max(len(self.doc_lens), 1)
        self.doc_freq: Counter[str] = Counter()
        for tokens in self.tokenized:
            self.doc_freq.update(set(tokens))

    def _idf(self, token: str) -> float:
        n_docs = len(self.records)
        df = self.doc_freq.get(token, 0)
        return math.log(1 + (n_docs - df + 0.5) / (df + 0.5))

    def _score_doc(self, query_tokens: list[str], doc_index: int) -> float:
        frequencies = Counter(self.tokenized[doc_index])
        doc_len = self.doc_lens[doc_index] or 1
        score = 0.0
        for token in query_tokens:
            tf = frequencies.get(token, 0)
            if tf == 0:
                continue
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / max(self.avgdl, 1))
            score += self._idf(token) * numerator / denominator
        return score

    def search(self, query: str, *, top_k: int) -> list[RetrievalHit]:
        query_tokens = tokenize(query)
        scored: list[tuple[int, float]] = []
        for idx, _record in enumerate(self.records):
            score = self._score_doc(query_tokens, idx)
            if score > 0:
                scored.append((idx, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        hits: list[RetrievalHit] = []
        for rank, (idx, score) in enumerate(scored[:top_k], start=1):
            record = self.records[idx]
            hits.append(
                RetrievalHit(
                    node_id=record["id"],
                    text=record["text"],
                    metadata=record["metadata"],
                    score=score,
                    source="bm25",
                    rank=rank,
                )
            )
        return hits

