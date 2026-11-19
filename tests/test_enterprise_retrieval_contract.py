import sqlite3
from pathlib import Path

from src.retrieval.bm25 import BM25Retriever
from src.retrieval.evidence_package import (
    EvidenceDecision,
    SlotStatus,
    assemble_evidence_package,
)
from src.retrieval.plan_schema import RetrievalPlan
from src.retrieval.metric_relevance import table_candidate_matches_slot
from src.retrieval.request_context import RetrievalFilter, RetrievalRequest
from src.retrieval.structured_gateway import SqliteStructuredDataProvider
from src.retrieval.types import RetrievalHit


def metadata(**overrides) -> dict:
    return {
        "tenant_id": "tenant-a",
        "acl_scope": "finance",
        "document_version": 1,
        "company_key": "amd",
        "fiscal_year": 2022,
        "retrieval_granularity": "child_chunk",
        **overrides,
    }


def test_bm25_filters_acl_and_scope_before_scoring() -> None:
    records = [
        {"id": "allowed", "text": "secret revenue", "metadata": metadata()},
        {
            "id": "wrong-tenant",
            "text": "secret revenue exact answer",
            "metadata": metadata(tenant_id="tenant-b"),
        },
        {
            "id": "wrong-year",
            "text": "secret revenue exact answer",
            "metadata": metadata(fiscal_year=2021),
        },
    ]
    retrieval_filter = RetrievalFilter.from_request_and_scope(
        RetrievalRequest(
            tenant_id="tenant-a",
            acl_scopes=("finance",),
            document_version=1,
        ),
        RetrievalPlan.model_validate(
            {
                "intent": "numeric_lookup",
                "scope": {"company": "amd", "fiscal_years": [2022]},
                "tools": ["chunk"],
            }
        ).scope,
    )

    hits = BM25Retriever(records).search(
        "secret revenue exact answer",
        top_k=5,
        retrieval_filter=retrieval_filter,
    )

    assert [hit.node_id for hit in hits] == ["allowed"]


def test_scope_relaxation_never_drops_security_or_company_boundaries() -> None:
    retrieval_filter = RetrievalFilter.from_request_and_scope(
        RetrievalRequest(
            tenant_id="tenant-a",
            acl_scopes=("finance",),
            document_version=3,
        ),
        RetrievalPlan.model_validate(
            {
                "intent": "forecast",
                "scope": {
                    "company": "AES Corporation",
                    "fiscal_years": [2023],
                    "document_types": ["annual report"],
                },
                "tools": ["chunk"],
            }
        ).scope,
    )

    relaxed = retrieval_filter.without_period_and_document_type()

    assert retrieval_filter.company_key == "aes"
    assert retrieval_filter.document_types == ("10k",)
    assert relaxed.tenant_id == "tenant-a"
    assert relaxed.acl_scopes == ("finance",)
    assert relaxed.company_key == "aes"
    assert relaxed.document_version == 3
    assert relaxed.fiscal_years == ()
    assert relaxed.document_types == ()


def create_structured_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE structured_facts (
                id TEXT PRIMARY KEY,
                tenant_id TEXT,
                acl_scope TEXT,
                company_key TEXT,
                fiscal_year INTEGER,
                quarter INTEGER,
                metric TEXT,
                value TEXT,
                unit TEXT,
                source_system TEXT,
                observed_at TEXT,
                valid_from_epoch INTEGER,
                valid_to_epoch INTEGER
            )
            """
        )
        connection.executemany(
            "INSERT INTO structured_facts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "visible",
                    "tenant-a",
                    "finance",
                    "amd",
                    2022,
                    None,
                    "current assets",
                    "100",
                    "USD million",
                    "erp",
                    "2022-12-31",
                    0,
                    None,
                ),
                (
                    "hidden",
                    "tenant-b",
                    "finance",
                    "amd",
                    2022,
                    None,
                    "current assets",
                    "999",
                    "USD million",
                    "erp",
                    "2022-12-31",
                    0,
                    None,
                ),
            ],
        )


def test_structured_sql_gateway_enforces_tenant_acl_and_period(tmp_path: Path) -> None:
    database = tmp_path / "facts.sqlite"
    create_structured_database(database)
    retrieval_filter = RetrievalFilter(
        tenant_id="tenant-a",
        acl_scopes=("finance",),
        company_key="amd",
        fiscal_years=(2022,),
        document_version=1,
        as_of_epoch=2_000_000_000,
    )

    hits = SqliteStructuredDataProvider(database).search(
        "AMD current assets",
        retrieval_filter=retrieval_filter,
        top_k=5,
    )

    assert [hit.node_id for hit in hits] == ["visible"]
    assert hits[0].metadata["retrieval_granularity"] == "structured_record"


def test_evidence_package_reports_qualified_and_missing_slots() -> None:
    plan = RetrievalPlan.model_validate(
        {
            "intent": "comparison",
            "tools": ["chunk", "table"],
            "evidence_slots": [
                {
                    "name": "reason",
                    "description": "management explanation",
                    "preferred_tool": "chunk",
                    "query": "why revenue changed",
                },
                {
                    "name": "amount",
                    "description": "revenue amount",
                    "preferred_tool": "table",
                    "query": "revenue amount",
                },
            ],
        }
    )
    hits = [
        RetrievalHit(
            "narrative",
            "Management explained why revenue changed.",
            metadata(),
            1.0,
            "test",
        )
    ]

    package = assemble_evidence_package(plan, hits)

    assert package.decision == EvidenceDecision.QUALIFIED
    assert package.completeness == 0.5
    assert package.slots[0].status == SlotStatus.FILLED
    assert package.slots[1].status == SlotStatus.MISSING


def test_evidence_package_detects_structured_value_conflict() -> None:
    plan = RetrievalPlan.model_validate(
        {
            "intent": "numeric_lookup",
            "tools": ["structured"],
            "evidence_slots": [
                {
                    "name": "headcount",
                    "description": "current headcount",
                    "preferred_tool": "structured",
                    "query": "current headcount",
                }
            ],
        }
    )
    hits = [
        RetrievalHit(
            value,
            f"headcount: {value}",
            metadata(
                retrieval_granularity="structured_record",
                metric="headcount",
                value=value,
            ),
            1.0,
            "structured_sql",
        )
        for value in ("100", "101")
    ]

    package = assemble_evidence_package(plan, hits)

    assert package.decision == EvidenceDecision.CONFLICT
    assert package.slots[0].status == SlotStatus.CONFLICTING


def test_multi_period_trend_is_not_treated_as_a_conflict() -> None:
    plan = RetrievalPlan.model_validate(
        {
            "intent": "trend",
            "scope": {"company": "3M", "fiscal_years": []},
            "tools": ["chunk"],
            "evidence_slots": [
                {
                    "name": "trend",
                    "description": "multi-year dividend trend",
                    "preferred_tool": "chunk",
                    "query": "dividend trend",
                }
            ],
        }
    )
    hits = [
        RetrievalHit(
            str(year),
            f"dividend trend {year}",
            metadata(fiscal_year=year),
            1.0,
            "test",
        )
        for year in (2022, 2023)
    ]

    package = assemble_evidence_package(plan, hits)

    assert package.decision == EvidenceDecision.ANSWERED


def test_table_slot_metric_ontology_rejects_similar_but_wrong_income_row() -> None:
    wrong = RetrievalHit(
        "net-income",
        "Row: Net income\nCells:\n- 2022: 100",
        metadata(retrieval_granularity="table_row", row_label="Net income"),
        1.0,
        "test",
    )
    correct = RetrievalHit(
        "operating-profit",
        "Row: Operating profit\nCells:\n- 2022: 120",
        metadata(
            retrieval_granularity="table_row",
            row_label="Operating profit",
        ),
        1.0,
        "test",
    )

    assert not table_candidate_matches_slot(
        "FY2022 operating income income statement",
        wrong,
    )
    assert table_candidate_matches_slot(
        "FY2022 operating income income statement",
        correct,
    )


def test_table_slot_metric_ontology_maps_capital_spending_to_capex() -> None:
    hit = RetrievalHit(
        "capex",
        "Row: Capital spending\nCells:\n- 2022: 500",
        metadata(
            retrieval_granularity="table_row",
            row_label="Capital spending",
        ),
        1.0,
        "test",
    )

    assert table_candidate_matches_slot(
        "FY2022 capital expenditures cash flow statement",
        hit,
    )


def test_quarter_constraint_is_not_satisfied_by_source_filename_alone() -> None:
    outlook = RetrievalHit(
        "outlook",
        "Source: ULTABEAUTY_2023Q4_EARNINGS.pdf\nRow: Share repurchases\n- FY23 Outlook: 900",
        metadata(
            retrieval_granularity="table_row",
            row_label="Share repurchases",
            surrounding_heading="Fiscal 2023 Outlook",
        ),
        1.0,
        "test",
    )
    actual = RetrievalHit(
        "actual",
        "Source: ULTABEAUTY_2023Q4_EARNINGS.pdf\n13 Weeks Ended\nRow: Share repurchases\n- 2023: 325",
        metadata(
            retrieval_granularity="table_row",
            row_label="Share repurchases",
        ),
        1.0,
        "test",
    )

    for query in (
        "Ulta Beauty stock repurchase spend Q4 FY 2023",
        "Ulta Beauty stock repurchase spend fourth quarter fiscal 2023",
    ):
        assert not table_candidate_matches_slot(query, outlook)
        assert table_candidate_matches_slot(query, actual)
