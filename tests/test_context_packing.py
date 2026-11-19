from src.retrieval.context_packing import (
    build_generation_context,
    constrain_hits_by_metadata,
    pack_contexts,
    select_structured_blocks,
    select_table_context,
)
from src.retrieval.types import RetrievalHit


def make_hit(
    node_id: str,
    text: str,
    metadata: dict,
    *,
    score: float = 1.0,
) -> RetrievalHit:
    return RetrievalHit(node_id, text, metadata, score, "test", 1)


def test_metadata_constraints_prefer_requested_annual_filing() -> None:
    hits = [
        make_hit("q", "Quarterly margin", {"file_name": "3M_2023Q2_10Q.pdf"}, score=2.0),
        make_hit("k", "Annual margin", {"file_name": "3M_2022_10K.pdf"}),
        make_hit("other", "Other company", {"file_name": "AES_2022_10K.pdf"}),
    ]

    constrained = constrain_hits_by_metadata(
        "According to 3M's FY2022 10-K, what drove operating margin?",
        hits,
    )

    assert [hit.node_id for hit in constrained] == ["k"]
    assert constrained[0].debug["metadata_constraint_form"] == "10k"


def test_table_context_preserves_header_and_adjacent_rows() -> None:
    text = """Heading: Balance Sheet
Table:
| Metric | 2022 | 2021 |
| --- | ---: | ---: |
| Cash | 100 | 90 |
| Total current liabilities | 200 | 180 |
| Long-term debt | 500 | 450 |
"""

    packed = select_table_context(text, {"Total current liabilities"}, max_chars=1000)

    assert "| Metric | 2022 | 2021 |" in packed
    assert "| Total current liabilities | 200 | 180 |" in packed
    assert "| Cash | 100 | 90 |" in packed


def test_structured_block_selection_keeps_neighboring_context() -> None:
    text = """Overview text that is unrelated.

Operating margin declined by 4 percentage points in 2022.

The decline was driven by litigation charges and impairment.

Governance information that is unrelated.
"""

    packed = select_structured_blocks("Why did operating margin decline in 2022?", text, max_chars=500)

    assert "Operating margin declined" in packed
    assert "litigation charges" in packed


def test_parent_child_context_uses_parent_table_for_row_hit() -> None:
    table_record = {
        "id": "table-parent",
        "text": """Heading: Balance Sheet
Table:
| Metric | 2022 |
| --- | ---: |
| Total current liabilities | 200 |
| Long-term debt | 500 |
""",
        "metadata": {
            "table_id": "table-1",
            "chunk_id": "table-1",
            "source_path": "AMD_2022_10K.pdf",
            "retrieval_granularity": "table",
        },
    }

    class Tables:
        def parent_table(self, table_id: str):
            return table_record if table_id == "table-1" else None

    child = make_hit(
        "row",
        "Row: Total current liabilities\nCells:\n- 2022: 200",
        {
            "table_id": "table-1",
            "row_label": "Total current liabilities",
            "source_path": "AMD_2022_10K.pdf",
            "retrieval_granularity": "table_row",
        },
    )

    contexts = build_generation_context(
        "What are total current liabilities for AMD in FY2022?",
        [child],
        parent_records=[],
        table_retriever=Tables(),
    )

    assert len(contexts) == 1
    assert contexts[0].metadata["parent_type"] == "table"
    assert "| Metric | 2022 |" in contexts[0].text
    assert "Total current liabilities" in contexts[0].text


def test_single_child_returns_complete_parent_chunk() -> None:
    parent = {
        "id": "parent-2",
        "text": (
            "Operating margin declined by four percentage points.\n\n"
            "The decline was caused by litigation charges and an impairment.\n\n"
            "Management expects part of the pressure to continue."
        ),
        "metadata": {
            "source_path": "3M_2022_10K.pdf",
            "page_number": 2,
            "retrieval_granularity": "parent_chunk",
        },
    }
    child = make_hit(
        "chunk-2",
        "The decline was caused by litigation charges and an impairment.",
        {
            "source_path": "3M_2022_10K.pdf",
            "page_number": 2,
            "parent_id": "parent-2",
            "retrieval_granularity": "child_chunk",
        },
    )

    contexts = build_generation_context(
        "Why did operating margin decline?",
        [child],
        parent_records=[parent],
        table_retriever=None,
    )

    assert contexts[0].metadata["parent_type"] == "parent_chunk"
    assert contexts[0].text == parent["text"]
    assert "Management expects" in contexts[0].text


def test_metadata_constraints_keep_calculation_evidence() -> None:
    calculation = make_hit(
        "calculation",
        "Deterministic calculation aid: quick ratio = 1.5",
        {"retrieval_granularity": "calculation"},
    )
    filing = make_hit(
        "filing",
        "AMD FY2022 current assets",
        {"source_path": "AMD_2022_10K.pdf"},
    )

    constrained = constrain_hits_by_metadata(
        "What was AMD's quick ratio in FY2022?",
        [filing, calculation],
    )

    assert {item.node_id for item in constrained} == {"filing", "calculation"}


def test_context_packing_keeps_ranked_child_anchors() -> None:
    child = make_hit(
        "child",
        "Exact child evidence that must survive packing.",
        {
            "source_path": "AMD_2022_10K.pdf",
            "page_number": 5,
            "retrieval_role": "child",
        },
        score=0.1,
    )
    supplement = make_hit(
        "table",
        "Highly scored supplemental table.",
        {
            "source_path": "AMD_2022_10K.pdf",
            "retrieval_role": "table_supplement",
        },
        score=1.0,
    )

    packed = pack_contexts("What did AMD report?", [supplement, child])

    assert packed[0].node_id == "child"
