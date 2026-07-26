from __future__ import annotations

import os
import re
from collections import Counter

from llama_index.core import Settings

from src.retrieval.bm25 import BM25Retriever
from src.retrieval.fusion import reciprocal_rank_fusion
from src.retrieval.page_retriever import PageRetriever
from src.retrieval.query_expansion import expand_financial_queries
from src.retrieval.reranker import build_reranker
from src.retrieval.table_retriever import TableRetriever
from src.retrieval.tokenizer import tokenize
from src.retrieval.types import RetrievalHit
from src.vector_store import get_chroma_collection


TABLE_QUERY_PATTERN = re.compile(
    r"\b("
    r"percent|percentage|ratio|margin|rate|increase|decrease|reduction|growth|"
    r"amount|balance|expense|sales|revenue|income|cash|assets|liabilities|"
    r"inventory|inventories|repurchase|capex|capital expenditures|ebitda|"
    r"statement|line item|table|fy20\d{2}|q[1-4]"
    r")\b|[%$]",
    re.I,
)


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


def source_key(metadata: dict) -> str:
    return str(metadata.get("source_path") or metadata.get("file_path") or metadata.get("file_name") or "")


def meaningful_tokens(text: str) -> list[str]:
    stopwords = {
        "about",
        "after",
        "also",
        "and",
        "are",
        "based",
        "between",
        "company",
        "does",
        "for",
        "from",
        "have",
        "how",
        "the",
        "this",
        "what",
        "when",
        "which",
        "with",
        "year",
    }
    return [
        token
        for token in tokenize(text)
        if len(token) > 2 and token not in stopwords and not re.fullmatch(r"20\d{2}|19\d{2}", token)
    ]


def clone_hit(hit: RetrievalHit) -> RetrievalHit:
    return RetrievalHit(
        node_id=hit.node_id,
        text=hit.text,
        metadata=dict(hit.metadata),
        score=hit.score,
        source=hit.source,
        rank=hit.rank,
        debug=dict(hit.debug),
    )


def should_search_tables(query: str) -> bool:
    return bool(TABLE_QUERY_PATTERN.search(query))


class HybridRetriever:
    def __init__(self) -> None:
        self.collection = get_chroma_collection()
        self.records = load_chroma_records()
        self.record_features = {
            record["id"]: {
                "tokens": set(meaningful_tokens(record.get("text") or "")),
                "numbers": set(re.findall(r"\d+(?:\.\d+)?%?", (record.get("text") or "").lower())),
            }
            for record in self.records
        }
        self._page_retriever: PageRetriever | None = None
        self._table_retriever: TableRetriever | None = None
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

    def source_sweep_search(
        self,
        queries: list[str],
        seed_hits: list[RetrievalHit],
        *,
        top_sources: int,
        top_k_per_source: int,
    ) -> list[RetrievalHit]:
        """Rescore chunks inside likely source PDFs to recover evidence pages.

        First-stage retrieval is good at finding the right filing, but table-heavy
        questions often need line items whose chunks do not repeat the user's
        wording. This sweep stays within likely sources and uses expanded finance
        terms to add evidence candidates before final reranking.
        """
        if top_sources <= 0 or top_k_per_source <= 0 or not seed_hits:
            return []

        source_votes: Counter[str] = Counter()
        for hit in seed_hits:
            source = source_key(hit.metadata)
            if source:
                source_votes[source] += max(1, top_sources + 1 - min(hit.rank or top_sources, top_sources))
        sources = [source for source, _count in source_votes.most_common(top_sources)]
        if not sources:
            return []

        query_text = " ".join(queries)
        query_tokens = set(meaningful_tokens(query_text))
        query_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", query_text.lower()))
        if not query_tokens and not query_numbers:
            return []

        scored: list[tuple[float, dict]] = []
        source_set = set(sources)
        for record in self.records:
            metadata = record.get("metadata") or {}
            if source_key(metadata) not in source_set:
                continue
            features = getattr(self, "record_features", {}).get(record["id"], {})
            text = record.get("text") or ""
            text_tokens = features.get("tokens") or set(meaningful_tokens(text))
            text_numbers = features.get("numbers") or set(re.findall(r"\d+(?:\.\d+)?%?", text.lower()))
            token_overlap = len(query_tokens & text_tokens) / max(len(query_tokens), 1)
            number_overlap = len(query_numbers & text_numbers) / max(len(query_numbers), 1) if query_numbers else 0.0
            table_bonus = 0.05 if re.search(r"\b(total|current|assets|liabilities|revenue|income|cash|inventor|depreciation|amortization|capital|margin|segment)\b", text, re.I) else 0.0
            score = token_overlap + 0.35 * number_overlap + table_bonus
            if score > 0:
                scored.append((score, record))

        scored.sort(key=lambda item: item[0], reverse=True)
        limit = top_sources * top_k_per_source
        hits: list[RetrievalHit] = []
        for rank, (score, record) in enumerate(scored[:limit], start=1):
            hits.append(
                RetrievalHit(
                    node_id=record["id"],
                    text=record["text"],
                    metadata=record["metadata"],
                    score=score,
                    source="source_sweep",
                    rank=rank,
                    debug={"source_sweep_score": score},
                )
            )
        return hits

    def search(self, query: str, *, expand_queries: bool | None = None) -> list[RetrievalHit]:
        vector_top_k = int(os.getenv("VECTOR_TOP_K", "20"))
        bm25_top_k = int(os.getenv("BM25_TOP_K", "20"))
        hybrid_top_k = int(os.getenv("HYBRID_TOP_K", "12"))
        final_top_k = int(os.getenv("TOP_K", "5"))
        rrf_k = int(os.getenv("RRF_K", "60"))
        reranker_enabled = os.getenv("RERANKER_ENABLED", "true").lower() == "true"
        if expand_queries is None:
            expand_queries = os.getenv("HYBRID_QUERY_EXPANSION_ENABLED", "true").lower() == "true"

        evidence_queries = expand_financial_queries(query) if expand_queries else [query]
        first_stage_expansion = os.getenv("HYBRID_FIRST_STAGE_QUERY_EXPANSION_ENABLED", "false").lower() == "true"
        first_stage_queries = evidence_queries if first_stage_expansion else [query]
        vector_ranked_lists = [self.vector_search(expanded_query, top_k=vector_top_k) for expanded_query in first_stage_queries]
        bm25_ranked_lists = [self.bm25.search(expanded_query, top_k=bm25_top_k) for expanded_query in first_stage_queries]
        fused = reciprocal_rank_fusion(
            [*vector_ranked_lists, *bm25_ranked_lists],
            top_k=hybrid_top_k,
            rrf_k=rrf_k,
        )

        rerank_query = (
            " ".join(evidence_queries)
            if os.getenv("HYBRID_RERANK_WITH_EXPANDED_QUERY", "true").lower() == "true"
            else query
        )
        protect_baseline = os.getenv("HYBRID_PROTECT_BASELINE_RESULTS", "false").lower() == "true"
        baseline_hits = []
        if protect_baseline:
            baseline_hits = (
                self.reranker.rerank(query, [clone_hit(hit) for hit in fused], top_k=final_top_k)
                if reranker_enabled
                else [clone_hit(hit) for hit in fused[:final_top_k]]
            )

        if os.getenv("SOURCE_SWEEP_ENABLED", "false").lower() == "true":
            sweep_hits = self.source_sweep_search(
                evidence_queries,
                fused,
                top_sources=int(os.getenv("SOURCE_SWEEP_TOP_SOURCES", "2")),
                top_k_per_source=int(os.getenv("SOURCE_SWEEP_TOP_K_PER_SOURCE", "12")),
            )
            if sweep_hits:
                fused = reciprocal_rank_fusion(
                    [fused, sweep_hits],
                    top_k=max(hybrid_top_k, final_top_k * 4),
                    rrf_k=rrf_k,
                )
                candidate_top_k = int(os.getenv("HYBRID_CANDIDATE_RERANK_TOP_K", str(final_top_k * 2)))
                candidate_hits = (
                    self.reranker.rerank(rerank_query, [clone_hit(hit) for hit in fused], top_k=candidate_top_k)
                    if reranker_enabled
                    else [clone_hit(hit) for hit in fused[:candidate_top_k]]
                )
                if protect_baseline:
                    return reciprocal_rank_fusion(
                        [baseline_hits, candidate_hits],
                        top_k=final_top_k,
                        rrf_k=int(os.getenv("FINAL_RRF_K", "30")),
                    )

        # Page evidence preserves table structure that can be split across
        # chunks. Ten pages materially improves evidence coverage on FinanceBench.
        page_top_k = int(os.getenv("HYBRID_PAGE_TOP_K", "10"))
        page_candidates: list[RetrievalHit] = []
        if page_top_k > 0:
            if self._page_retriever is None:
                self._page_retriever = PageRetriever()
            page_candidates = self._page_retriever.search(query, top_k=page_top_k)

        hits = self.reranker.rerank(rerank_query, fused, top_k=final_top_k) if reranker_enabled else fused[:final_top_k]
        if page_candidates:
            existing_ids = {hit.node_id for hit in hits}
            for page_hit in page_candidates:
                if page_hit.node_id in existing_ids:
                    continue
                page_hit.rank = len(hits) + 1
                hits.append(page_hit)
                existing_ids.add(page_hit.node_id)

        # Row-level table evidence keeps financial labels, periods, and values
        # together when a regular text chunk splits a statement table.
        table_top_k = int(os.getenv("HYBRID_TABLE_TOP_K", "3"))
        if table_top_k > 0 and should_search_tables(query):
            if self._table_retriever is None:
                self._table_retriever = TableRetriever()
            table_candidates = self._table_retriever.search(query, top_k=table_top_k * 4)
            retrieved_sources = {source_key(hit.metadata) for hit in hits if source_key(hit.metadata)}
            if retrieved_sources:
                table_candidates = [
                    hit for hit in table_candidates if source_key(hit.metadata) in retrieved_sources
                ]

            existing_ids = {hit.node_id for hit in hits}
            for table_hit in table_candidates[:table_top_k]:
                if table_hit.node_id in existing_ids:
                    continue
                table_hit.rank = len(hits) + 1
                hits.append(table_hit)
                existing_ids.add(table_hit.node_id)
        return hits


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
