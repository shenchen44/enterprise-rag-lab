from __future__ import annotations

from dataclasses import dataclass

from src.retrieval.context_packing import build_generation_context
from src.retrieval.evidence_package import EvidencePackage, assemble_evidence_package
from src.retrieval.executor import RetrievalExecutor
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.plan_schema import RetrievalPlan
from src.retrieval.planner import LLMRetrievalPlanner, RetrievalPlanner
from src.retrieval.request_context import RetrievalFilter, RetrievalRequest
from src.retrieval.structured_gateway import StructuredDataGateway
from src.retrieval.table_retriever import TableRetriever
from src.retrieval.types import RetrievalHit


@dataclass(slots=True)
class EvidenceResult:
    plan: RetrievalPlan
    raw_hits: list[RetrievalHit]
    hits: list[RetrievalHit]
    package: EvidencePackage


class EvidenceRetriever:
    """Plan, execute, and assemble bounded evidence for answer generation."""

    def __init__(
        self,
        *,
        chunks: HybridRetriever | None = None,
        tables: TableRetriever | None = None,
        structured: StructuredDataGateway | None = None,
        planner: RetrievalPlanner | None = None,
    ) -> None:
        self.chunks = chunks or HybridRetriever()
        self.tables = tables or TableRetriever()
        self.planner = planner or LLMRetrievalPlanner()
        self.structured = structured or StructuredDataGateway()
        self.executor = RetrievalExecutor(
            chunks=self.chunks,
            tables=self.tables,
            structured=self.structured,
        )

    def retrieve(
        self,
        question: str,
        *,
        table_top_k: int = 3,
        pack_context: bool = True,
        request: RetrievalRequest | None = None,
    ) -> EvidenceResult:
        plan = self.planner.plan(question)
        retrieval_filter = RetrievalFilter.from_request_and_scope(
            request or RetrievalRequest.from_env(),
            plan.scope,
        )
        executed = self.executor.execute(
            question,
            plan,
            table_top_k=table_top_k,
            retrieval_filter=retrieval_filter,
        )
        hits = executed.hits
        if pack_context:
            hits = build_generation_context(
                question,
                hits,
                parent_records=self.chunks.parent_records,
                table_retriever=self.tables,
            )
        for rank, hit in enumerate(hits, start=1):
            hit.rank = rank
        return EvidenceResult(
            plan=plan,
            raw_hits=executed.raw_hits,
            hits=hits,
            package=assemble_evidence_package(plan, hits),
        )
