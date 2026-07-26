from src.retrieval.hybrid import HybridRetriever, should_search_tables
from src.retrieval.query_expansion import expand_financial_queries
from src.retrieval.types import RetrievalHit


def test_financial_query_expansion_adds_formula_inputs() -> None:
    expanded = " ".join(
        expand_financial_queries("Does AMD have a healthy quick ratio in FY2022?")
    ).lower()

    assert "total current assets" in expanded
    assert "current liabilities" in expanded
    assert "inventories" in expanded


def test_table_search_gate_targets_financial_evidence_questions() -> None:
    assert should_search_tables("What was AMD's gross margin in FY2022?")
    assert should_search_tables("How much cash did the company have?")
    assert not should_search_tables("Who was the company's chief executive officer?")


def test_source_sweep_recovers_evidence_inside_seed_source() -> None:
    retriever = HybridRetriever.__new__(HybridRetriever)
    retriever.records = [
        {
            "id": "overview",
            "text": "AMD business overview and risk factors.",
            "metadata": {"source_path": "AMD_2022_10K.pdf", "page_label": "3"},
        },
        {
            "id": "balance-sheet",
            "text": "Consolidated balance sheet total current assets inventories total current liabilities cash receivables.",
            "metadata": {"source_path": "AMD_2022_10K.pdf", "page_label": "56"},
        },
        {
            "id": "other",
            "text": "Total current assets and liabilities for another company.",
            "metadata": {"source_path": "OTHER_2022_10K.pdf", "page_label": "10"},
        },
    ]
    seed_hits = [
        RetrievalHit(
            node_id="overview",
            text="AMD business overview and risk factors.",
            metadata={"source_path": "AMD_2022_10K.pdf", "page_label": "3"},
            score=1.0,
            source="hybrid_rrf",
            rank=1,
        )
    ]

    hits = retriever.source_sweep_search(
        expand_financial_queries("Does AMD have a healthy quick ratio in FY2022?"),
        seed_hits,
        top_sources=1,
        top_k_per_source=2,
    )

    assert hits
    assert hits[0].node_id == "balance-sheet"
    assert all(hit.metadata["source_path"] == "AMD_2022_10K.pdf" for hit in hits)
