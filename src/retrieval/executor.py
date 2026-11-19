from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from src.retrieval.financial_calculator import append_calculation_hit
from src.retrieval.fusion import reciprocal_rank_fusion
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.metric_relevance import table_candidate_matches_slot
from src.retrieval.plan_schema import RetrievalPlan, RetrievalTool
from src.retrieval.request_context import RetrievalFilter
from src.retrieval.structured_gateway import StructuredDataGateway
from src.retrieval.table_retriever import TableRetriever
from src.retrieval.types import RetrievalHit


def source_name(metadata: dict) -> str:
    source = str(
        metadata.get("source_path")
        or metadata.get("file_path")
        or metadata.get("file_name")
        or ""
    )
    return Path(source).name.lower()


def tag_slot(hit: RetrievalHit, slot_name: str) -> None:
    names = set(hit.metadata.get("evidence_slot_names") or [])
    names.add(slot_name)
    hit.metadata["evidence_slot_names"] = sorted(names)
    hit.metadata["retrieval_role"] = "slot_anchor"
    hit.debug["slot_relevance_score"] = hit.score


def merge_hits(
    reserved: list[RetrievalHit],
    general: list[RetrievalHit],
) -> list[RetrievalHit]:
    """Keep one copy of each hit while preserving all slot assignments."""
    merged: dict[str, RetrievalHit] = {}
    order: list[str] = []
    for hit in [*reserved, *general]:
        existing = merged.get(hit.node_id)
        if existing is None:
            merged[hit.node_id] = hit
            order.append(hit.node_id)
            continue
        names = set(existing.metadata.get("evidence_slot_names") or [])
        names.update(hit.metadata.get("evidence_slot_names") or [])
        if names:
            existing.metadata["evidence_slot_names"] = sorted(names)
            existing.metadata["retrieval_role"] = "slot_anchor"
    hits = [merged[node_id] for node_id in order]
    for rank, hit in enumerate(hits, start=1):
        hit.rank = rank
    return hits


@dataclass(slots=True)
class ExecutedRetrieval:
    raw_hits: list[RetrievalHit]
    hits: list[RetrievalHit]


class RetrievalExecutor:
    def __init__(
        self,
        *,
        chunks: HybridRetriever,
        tables: TableRetriever,
        structured: StructuredDataGateway,
    ) -> None:
        self.chunks = chunks
        self.tables = tables
        self.structured = structured

    def execute(
        self,
        question: str,
        plan: RetrievalPlan,
        *,
        table_top_k: int,
        retrieval_filter: RetrievalFilter,
    ) -> ExecutedRetrieval:
        child_hits: list[RetrievalHit] = []
        if plan.uses(RetrievalTool.CHUNK):
            general_child_hits = self.chunks.search_many(
                list(dict.fromkeys([question, *plan.queries.chunk])),
                rerank_query=question,
                retrieval_filter=retrieval_filter,
            )
            for hit in general_child_hits:
                hit.metadata["retrieval_role"] = "child"

            reserved_child_hits: list[RetrievalHit] = []
            for slot in plan.evidence_slots:
                if slot.preferred_tool != RetrievalTool.CHUNK:
                    continue
                slot_hits = self.chunks.search_many(
                    [slot.query],
                    rerank_query=slot.query,
                    retrieval_filter=retrieval_filter,
                )
                if slot_hits:
                    tag_slot(slot_hits[0], slot.name)
                    reserved_child_hits.append(slot_hits[0])
            child_hits = merge_hits(reserved_child_hits, general_child_hits)

        table_hits: list[RetrievalHit] = []
        if table_top_k > 0 and plan.uses(RetrievalTool.TABLE):
            source_scope = {source_name(hit.metadata) for hit in child_hits}

            def in_source_scope(hit: RetrievalHit) -> bool:
                return not source_scope or source_name(hit.metadata) in source_scope

            table_lists = [
                self.tables.search_rows(
                    query,
                    top_k=max(table_top_k * 4, table_top_k),
                    retrieval_filter=retrieval_filter,
                )
                for query in list(dict.fromkeys([question, *plan.queries.table]))
            ]
            table_candidates = reciprocal_rank_fusion(
                table_lists,
                top_k=max(table_top_k * 4, table_top_k),
                rrf_k=int(os.getenv("RRF_K", "60")),
            )
            scoped = [hit for hit in table_candidates if in_source_scope(hit)]
            if scoped and os.getenv("RERANKER_ENABLED", "true").lower() == "true":
                general_table_hits = self.chunks.reranker.rerank(
                    question,
                    scoped,
                    top_k=table_top_k,
                )
            else:
                general_table_hits = scoped[:table_top_k]
            for hit in general_table_hits:
                hit.metadata["retrieval_role"] = "table_supplement"

            reserved_table_hits: list[RetrievalHit] = []
            for slot in plan.evidence_slots:
                if slot.preferred_tool != RetrievalTool.TABLE:
                    continue
                slot_candidates = [
                    hit
                    for hit in self.tables.search_rows(
                        slot.query,
                        top_k=max(table_top_k * 4, table_top_k),
                        retrieval_filter=retrieval_filter,
                    )
                    if in_source_scope(hit)
                ]
                if not slot_candidates:
                    continue
                if os.getenv("RERANKER_ENABLED", "true").lower() == "true":
                    slot_candidates = self.chunks.reranker.rerank(
                        slot.query,
                        slot_candidates,
                        top_k=min(8, len(slot_candidates)),
                    )
                matching_candidates = [
                    hit
                    for hit in slot_candidates
                    if table_candidate_matches_slot(slot.query, hit)
                ]
                for hit in matching_candidates[:2]:
                    tag_slot(hit, slot.name)
                    reserved_table_hits.append(hit)
            table_hits = merge_hits(reserved_table_hits, general_table_hits)

        structured_hits: list[RetrievalHit] = []
        if plan.uses(RetrievalTool.STRUCTURED):
            structured_lists = [
                self.structured.search(
                    query,
                    retrieval_filter=retrieval_filter,
                    top_k=table_top_k,
                )
                for query in plan.queries_for(RetrievalTool.STRUCTURED, question)
            ]
            structured_hits = reciprocal_rank_fusion(
                structured_lists,
                top_k=table_top_k,
                rrf_k=int(os.getenv("RRF_K", "60")),
            )

        raw_hits = [*child_hits, *table_hits, *structured_hits]
        hits = list(raw_hits)
        if plan.requires_calculation or plan.uses(RetrievalTool.CALCULATOR):
            hits = append_calculation_hit(question, hits)
            calculator_slots = [
                slot.name
                for slot in plan.evidence_slots
                if slot.preferred_tool == RetrievalTool.CALCULATOR
            ]
            for hit in hits:
                if hit.metadata.get("retrieval_granularity") != "calculation":
                    continue
                for slot_name in calculator_slots:
                    tag_slot(hit, slot_name)
        return ExecutedRetrieval(raw_hits=raw_hits, hits=hits)
