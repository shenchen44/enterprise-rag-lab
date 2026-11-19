from src.retrieval.evidence import EvidenceRetriever
from src.retrieval.plan_schema import RetrievalPlan
from src.retrieval.types import RetrievalHit


def hit(node_id: str, text: str, metadata: dict, score: float = 1.0) -> RetrievalHit:
    return RetrievalHit(node_id, text, metadata, score, "test", 1)


class Planner:
    def __init__(self, plan: RetrievalPlan) -> None:
        self.value = plan

    def plan(self, _question: str) -> RetrievalPlan:
        return self.value


class Reranker:
    def rerank(self, _query: str, hits: list[RetrievalHit], *, top_k: int):
        return hits[:top_k]


class Chunks:
    reranker = Reranker()
    records: list[dict] = []
    parent_records = [
        {
            "id": "parent",
            "text": "AMD reported current assets and liabilities in FY2022.",
            "metadata": {
                "source_path": "AMD_2022_10K.pdf",
                "page_number": 56,
                "retrieval_granularity": "parent_chunk",
            },
        }
    ]

    def __init__(self) -> None:
        self.queries: list[str] = []

    def search_many(
        self,
        queries: list[str],
        *,
        rerank_query: str,
        retrieval_filter=None,
    ):
        self.queries = queries
        return [
            hit(
                "chunk",
                "AMD reported current assets in FY2022.",
                {
                    "source_path": "AMD_2022_10K.pdf",
                    "page_number": 56,
                    "parent_id": "parent",
                    "retrieval_granularity": "child_chunk",
                },
            )
        ]


class Tables:
    def __init__(self) -> None:
        self.row_searches = 0

    def search_rows(self, _query: str, *, top_k: int, retrieval_filter=None):
        self.row_searches += 1
        return [
            hit(
                "row",
                "Row: Total current assets\nCells:\n- 2022: 100",
                {
                    "source_path": "AMD_2022_10K.pdf",
                    "table_id": "table",
                    "row_label": "Total current assets",
                    "retrieval_granularity": "table_row",
                },
            )
        ]

    def parent_table(self, table_id: str):
        if table_id != "table":
            return None
        return {
            "id": "table",
            "text": (
                "| Metric | 2022 |\n"
                "| --- | ---: |\n"
                "| Total current assets | 100 |\n"
                "| Total current liabilities | 50 |"
            ),
            "metadata": {
                "source_path": "AMD_2022_10K.pdf",
                "table_id": "table",
                "retrieval_granularity": "table",
            },
        }


def test_agent_table_plan_returns_parent_table() -> None:
    tables = Tables()
    plan = RetrievalPlan.model_validate(
        {
            "intent": "numeric_lookup",
            "tools": ["chunk", "table"],
            "queries": {"chunk": [], "table": ["current assets 2022"]},
        }
    )
    retriever = EvidenceRetriever(
        chunks=Chunks(),
        tables=tables,
        planner=Planner(plan),
    )

    result = retriever.retrieve(
        "What was AMD's current assets in FY2022?",
        table_top_k=1,
    )

    assert tables.row_searches > 0
    table_context = next(
        context for context in result.hits
        if context.metadata["parent_type"] == "table"
    )
    assert "| Metric | 2022 |" in table_context.text
    assert "Total current assets" in table_context.text


def test_narrative_plan_does_not_call_table_retrieval() -> None:
    tables = Tables()
    plan = RetrievalPlan.model_validate(
        {
            "intent": "narrative_fact",
            "tools": ["chunk"],
            "queries": {
                "chunk": ["AMD major products and services"],
                "table": [],
            },
        }
    )
    retriever = EvidenceRetriever(
        chunks=Chunks(),
        tables=tables,
        planner=Planner(plan),
    )

    result = retriever.retrieve("What products does AMD sell?")

    assert result.plan.intent == "narrative_fact"
    assert tables.row_searches == 0
    assert result.hits[0].metadata["parent_type"] == "parent_chunk"


def test_slot_aware_chunk_retrieval_preserves_each_parent() -> None:
    class SlotChunks(Chunks):
        parent_records = [
            {
                "id": "assets-parent",
                "text": "AMD current assets were 100.",
                "metadata": {
                    "source_path": "AMD_2022_10K.pdf",
                    "retrieval_granularity": "parent_chunk",
                },
            },
            {
                "id": "liabilities-parent",
                "text": "AMD current liabilities were 50.",
                "metadata": {
                    "source_path": "AMD_2022_10K.pdf",
                    "retrieval_granularity": "parent_chunk",
                },
            },
        ]

        def search_many(
            self,
            queries: list[str],
            *,
            rerank_query: str,
            retrieval_filter=None,
        ):
            query = " ".join(queries).lower()
            if "liabilities" in query:
                return [
                    hit(
                        "liabilities",
                        "current liabilities 50",
                        {
                            "source_path": "AMD_2022_10K.pdf",
                            "parent_id": "liabilities-parent",
                            "retrieval_granularity": "child_chunk",
                        },
                    )
                ]
            return [
                hit(
                    "assets",
                    "current assets 100",
                    {
                        "source_path": "AMD_2022_10K.pdf",
                        "parent_id": "assets-parent",
                        "retrieval_granularity": "child_chunk",
                    },
                )
            ]

    plan = RetrievalPlan.model_validate(
        {
            "intent": "financial_calculation",
            "tools": ["chunk"],
            "evidence_slots": [
                {
                    "name": "assets",
                    "description": "current assets",
                    "preferred_tool": "chunk",
                    "query": "current assets",
                },
                {
                    "name": "liabilities",
                    "description": "current liabilities",
                    "preferred_tool": "chunk",
                    "query": "current liabilities",
                },
            ],
        }
    )

    result = EvidenceRetriever(
        chunks=SlotChunks(),
        tables=Tables(),
        planner=Planner(plan),
    ).retrieve("Calculate the current ratio.")

    assert {slot.status.value for slot in result.package.slots} == {"filled"}
    assert {hit.node_id for hit in result.hits} == {
        "assets-parent",
        "liabilities-parent",
    }


def test_multiple_table_slots_merge_into_one_parent_table() -> None:
    class SlotTables(Tables):
        def search_rows(self, query: str, *, top_k: int, retrieval_filter=None):
            label = (
                "Total current liabilities"
                if "liabilities" in query.lower()
                else "Total current assets"
            )
            value = "50" if "liabilities" in query.lower() else "100"
            return [
                hit(
                    label,
                    f"Row: {label}\nCells:\n- 2022: {value}",
                    {
                        "source_path": "AMD_2022_10K.pdf",
                        "table_id": "table",
                        "row_label": label,
                        "retrieval_granularity": "table_row",
                    },
                )
            ]

    plan = RetrievalPlan.model_validate(
        {
            "intent": "financial_calculation",
            "tools": ["table"],
            "evidence_slots": [
                {
                    "name": "assets",
                    "description": "current assets",
                    "preferred_tool": "table",
                    "query": "current assets",
                },
                {
                    "name": "liabilities",
                    "description": "current liabilities",
                    "preferred_tool": "table",
                    "query": "current liabilities",
                },
            ],
        }
    )

    result = EvidenceRetriever(
        chunks=Chunks(),
        tables=SlotTables(),
        planner=Planner(plan),
    ).retrieve("Calculate the current ratio.", table_top_k=1)

    assert len(result.hits) == 1
    assert result.hits[0].metadata["evidence_slot_names"] == [
        "assets",
        "liabilities",
    ]
    assert "Total current assets" in result.hits[0].text
    assert "Total current liabilities" in result.hits[0].text
