import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.retrieval.source_period import (
    parse_query_scope,
    parse_source_profile,
    rerank_by_source_period,
)
from src.retrieval.types import RetrievalHit


def test_parse_query_scope_normalizes_company_and_year() -> None:
    scope = parse_query_scope(
        "What drove operating margin change in AMEX's FY22 10-K?"
    )

    assert scope.company == "americanexpress"
    assert scope.fiscal_years == frozenset({2022})
    assert scope.annual_requested is True


def test_fiscal_year_does_not_force_a_ten_k() -> None:
    scope = parse_query_scope("What drove SG&A expense in FY2023?")

    assert scope.fiscal_years == frozenset({2023})
    assert scope.annual_requested is False


def test_parse_source_profile_from_financebench_file_name() -> None:
    profile = parse_source_profile({"file_name": "3M_2023Q2_10Q.pdf"})

    assert profile.company == "3m"
    assert profile.fiscal_year == 2023
    assert profile.quarter == 2
    assert profile.form_type == "10q"


def test_source_period_routing_prefers_matching_annual_source() -> None:
    previous = os.environ.get("SOURCE_PERIOD_FILTER_ENABLED")
    os.environ["SOURCE_PERIOD_FILTER_ENABLED"] = "true"
    hits = [
        RetrievalHit(
            node_id="q2",
            text="3M Q2 2023 evidence",
            metadata={"file_name": "3M_2023Q2_10Q.pdf"},
            score=0.99,
            source="test",
            rank=1,
        ),
        RetrievalHit(
            node_id="fy",
            text="3M FY2022 evidence",
            metadata={"file_name": "3M_2022_10K.pdf"},
            score=0.8,
            source="test",
            rank=2,
        ),
        RetrievalHit(
            node_id="aes",
            text="AES evidence",
            metadata={"file_name": "AES_2022_10K.pdf"},
            score=0.95,
            source="test",
            rank=3,
        ),
    ]

    try:
        routed = rerank_by_source_period(
            "According to 3M's FY2022 10-K, is the business capital intensive?",
            hits,
        )
    finally:
        if previous is None:
            os.environ.pop("SOURCE_PERIOD_FILTER_ENABLED", None)
        else:
            os.environ["SOURCE_PERIOD_FILTER_ENABLED"] = previous

    assert [hit.node_id for hit in routed] == ["fy"]
