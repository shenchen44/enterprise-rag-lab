from src.eval.retrieval_metrics import (
    content_terms,
    evaluate_chunking,
    page_matches,
    term_recall,
    retrieval_metrics_for_hits,
)
from src.retrieval.types import RetrievalHit


def hit(text: str, metadata: dict, rank: int = 1) -> RetrievalHit:
    return RetrievalHit(
        node_id=f"node-{rank}",
        text=text,
        metadata=metadata,
        score=1.0,
        source="test",
        rank=rank,
    )


def test_page_matches_accepts_zero_based_financebench_pages() -> None:
    assert page_matches({"page_number": 1}, [0]) is True
    assert page_matches({"page_number": 47}, [47]) is True
    assert page_matches({"page_label": "p. 48"}, [47]) is True
    assert page_matches({"page_number": 10}, [47]) is False


def test_retrieval_metrics_score_source_page_and_reference_terms() -> None:
    item = {
        "question": "What drove operating margin?",
        "expected_sources": ["3M_2022_10K.pdf"],
        "expected_pages": [26],
        "reference_answer": "Operating margin decreased due to litigation and impairment charges.",
    }
    hits = [
        hit("unrelated cover page", {"source_path": "other.pdf", "page_number": 1}, rank=1),
        hit(
            "Operating margin decreased because of litigation and impairment charges.",
            {"source_path": "ui/data/3M_2022_10K.pdf", "page_number": 27},
            rank=2,
        ),
    ]

    metrics = retrieval_metrics_for_hits(item, hits)

    assert metrics["source_hit"] is True
    assert metrics["source_first_rank"] == 2
    assert metrics["page_hit"] is True
    assert metrics["page_first_rank"] == 2
    assert metrics["expected_page_recall"] == 1.0
    assert metrics["reference_term_recall"] > 0.5
    assert "litigation" in metrics["matched_reference_terms"]


def test_chunking_metrics_detect_evidence_page_coverage() -> None:
    questions = [
        {
            "question": "What was the quick ratio?",
            "expected_sources": ["AMD_2022_10K.pdf"],
            "expected_pages": [55],
            "reference_answer": "The quick ratio is 1.57 using cash, investments, receivables, and current liabilities.",
        }
    ]
    records = [
        {
            "id": "a",
            "text": "cash investments receivables current liabilities quick ratio",
            "metadata": {
                "source_path": "ui/data/financebench/AMD_2022_10K.pdf",
                "page_number": 56,
                "chunk_index": 1,
            },
        },
        {
            "id": "b",
            "text": "risk factors",
            "metadata": {
                "source_path": "ui/data/financebench/AMD_2022_10K.pdf",
                "page_number": 12,
                "chunk_index": 2,
            },
        },
    ]

    result = evaluate_chunking(records, questions)

    assert result["source_chunk_coverage"] == 1.0
    assert result["evidence_page_coverage"] == 1.0
    assert result["page_metadata_coverage"] == 1.0
    assert result["empty_chunk_ratio"] == 0.0
    assert result["median_chunk_chars"] is not None


def test_chunking_metrics_report_evidence_page_coverage_per_question() -> None:
    questions = [
        {
            "question": "What changed the effective tax rate?",
            "expected_sources": ["ACME_2022_10K.pdf"],
            "expected_pages": [40],
            "reference_answer": "The effective tax rate changed because income tax benefit and loss before income taxes moved materially.",
        }
    ]
    records = [
        {
            "id": "left",
            "text": "Effective tax rate changed because income tax benefit",
            "metadata": {
                "source_path": "ACME_2022_10K.pdf",
                "page_number": 41,
                "chunk_index": 1,
            },
        },
        {
            "id": "right",
            "text": "and loss before income taxes moved materially.",
            "metadata": {
                "source_path": "ACME_2022_10K.pdf",
                "page_number": 41,
                "chunk_index": 2,
            },
        },
    ]

    result = evaluate_chunking(records, questions)
    row_metrics = result["rows"][0]["chunking_metrics"]

    assert row_metrics["source_chunk_count"] == 2
    assert row_metrics["evidence_chunk_count"] == 2
    assert row_metrics["expected_page_coverage"] == 1.0


def test_reference_terms_include_financial_numbers() -> None:
    terms = content_terms("EBITDA less capex was $9,068.00 and margin was 16.5% in FY2022.")
    recall, matched = term_recall(terms, "The table reports EBITDA less capex of $9,068 and a 16.5% margin.")

    assert "9068" in terms
    assert "16.5" in terms
    assert "2022" not in terms
    assert recall is not None
    assert recall > 0.5
    assert "16.5" in matched
