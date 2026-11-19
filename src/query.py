from typing import Any, Optional

from llama_index.core.base.base_query_engine import BaseQueryEngine
from llama_index.core.indices.base import BaseIndex
from llama_index.core.query_engine import CustomQueryEngine
from llama_index.core.tools.query_engine import QueryEngineTool

from src.retrieval.evidence import EvidenceRetriever
from src.retrieval.hybrid import format_hits_as_evidence


class HybridRAGQueryEngine(CustomQueryEngine):
    """Query engine backed by Chroma vector search + BM25 + RRF + reranker."""

    retriever: EvidenceRetriever

    def custom_query(self, query_str: str) -> str:
        result = self.retriever.retrieve(query_str)
        return format_hits_as_evidence(
            query_str,
            result.hits,
            package=result.package,
        )


def create_query_engine(index: BaseIndex, **kwargs: Any) -> BaseQueryEngine:
    """
    Create a query engine for the given index.

    Args:
        index: The index to create a query engine for.
        params (optional): Additional parameters for the query engine, e.g: similarity_top_k

    The `index` argument is kept for compatibility with the generated template,
    but retrieval is handled by HybridRetriever directly against Chroma so the
    flow is explicit and easy to study.
    """
    return HybridRAGQueryEngine(retriever=EvidenceRetriever())


def get_query_engine_tool(
    index: BaseIndex,
    name: Optional[str] = None,
    description: Optional[str] = None,
    **kwargs: Any,
) -> QueryEngineTool:
    """
    Get a query engine tool for the given index.

    Args:
        index: The index to create a query engine for.
        name (optional): The name of the tool.
        description (optional): The description of the tool.
    """
    if name is None:
        name = "query_index"
    if description is None:
        description = (
            "Use this tool to retrieve cited evidence from the enterprise knowledge base. "
            "It performs Chroma vector search, BM25 keyword search, RRF hybrid fusion, "
            "and reranking. The output includes [citation:chunk_id] markers that must "
            "be preserved in the final answer."
        )
    query_engine = create_query_engine(index, **kwargs)
    tool = QueryEngineTool.from_defaults(
        query_engine=query_engine,
        name=name,
        description=description,
    )
    return tool
