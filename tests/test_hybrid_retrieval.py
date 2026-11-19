from src.retrieval.plan_schema import RetrievalPlan, RetrievalTool
from src.retrieval.planner import (
    LLMRetrievalPlanner,
    ReplayRetrievalPlanner,
    parse_plan_response,
)


def test_planner_response_selects_table_without_keyword_rules() -> None:
    plan = parse_plan_response(
        """```json
        {
          "intent": "numeric_lookup",
          "scope": {"company": "AMD", "fiscal_years": [2022]},
          "tools": ["chunk", "table"],
          "evidence_slots": [{
            "name": "current_assets",
            "description": "AMD total current assets for FY2022",
            "preferred_tool": "table",
            "query": "AMD total current assets 2022"
          }],
          "queries": {
            "chunk": ["AMD liquidity FY2022"],
            "table": ["total current assets 2022"]
          },
          "requires_calculation": false
        }
        ```"""
    )

    assert plan.uses(RetrievalTool.TABLE)
    assert plan.evidence_slots[0].name == "current_assets"
    assert plan.queries_for(RetrievalTool.TABLE, "original")[0] == "original"


def test_planner_failure_uses_bounded_fallback() -> None:
    class BrokenLLM:
        def complete(self, _prompt: str):
            return "not json"

    plan = LLMRetrievalPlanner(llm=BrokenLLM()).plan("Who is the CEO?")

    assert plan.planner_status == "fallback"
    assert set(plan.tools) == set(RetrievalTool)
    assert plan.planner_error == "ValueError: Planner response did not contain a JSON object."


def test_llm_planner_returns_validated_plan() -> None:
    class ValidLLM:
        calls = 0

        def complete(self, prompt: str, **_kwargs):
            self.calls += 1
            assert "Who is the CEO?" in prompt
            return """{
              "intent": "narrative_fact",
              "tools": ["chunk"],
              "evidence_slots": [],
              "queries": {
                "chunk": ["company chief executive officer"],
                "table": []
              },
              "requires_calculation": false
            }"""

    llm = ValidLLM()
    planner = LLMRetrievalPlanner(llm=llm)
    plan = planner.plan("Who is the CEO?")
    cached = planner.plan("Who is the CEO?")

    assert plan.planner_status == "planned"
    assert plan.tools == [RetrievalTool.CHUNK]
    assert cached == plan
    assert llm.calls == 1


def test_plan_schema_normalizes_bounded_llm_output() -> None:
    plan = RetrievalPlan.model_validate(
        {
            "intent": "comparison",
            "scope": {
                "fiscal_years": [2020, 2021, 2022, 2023, 2024],
                "quarter": "Q2",
            },
            "tools": ["table"],
            "queries": {
                "table": ["q1", "q2", "q3", "q4", "q5", "q6"],
            },
        }
    )

    assert plan.scope.quarter == 2
    assert plan.scope.fiscal_years == [2020, 2021, 2022, 2023]
    assert plan.queries.table == ["q1", "q2", "q3", "q4"]


def test_replay_planner_returns_saved_plan() -> None:
    saved = RetrievalPlan.model_validate(
        {"intent": "narrative_fact", "tools": ["chunk"]}
    )
    planner = ReplayRetrievalPlanner({"question": saved})

    assert planner.plan("question") == saved
    assert planner.plan("missing").planner_status == "fallback"
