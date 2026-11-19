from __future__ import annotations

import json
from typing import Protocol

from llama_index.core import Settings

from src.retrieval.plan_schema import RetrievalPlan


PLANNER_PROMPT = """You are the retrieval planner for an enterprise financial PDF RAG system.

Create a bounded retrieval plan. Do not answer the question.

Available tools:
- chunk: narrative facts and local passages; small child chunks are searched and
  their complete parent chunks are returned for generation
- table: numeric line items, comparisons, statement rows, and column headers
- structured: current or rapidly changing facts from governed SQL/API systems
- calculator: deterministic arithmetic after evidence retrieval

Instructions:
1. Extract company, fiscal years, quarter, and explicitly requested document types.
2. Decompose multi-hop questions into the smallest evidence slots required to answer.
3. Select one or more tools. Use structured for live/current operational facts;
   do not use it for facts frozen inside historical filings.
4. Write short semantic retrieval queries for each selected retriever. Do not append generic keyword lists.
5. Use at most 3 chunk queries, 4 table queries, 4 structured queries, and 6 evidence slots.
6. Set requires_calculation when arithmetic, a ratio, a percentage, a trend
   derived from values, or a largest/smallest ranking across table rows must be computed.
   A question asking "what drove" or "why" is narrative_fact, even when it names
   a financial metric; do not mark it as calculation unless arithmetic is requested.
7. Evidence slots must represent atomic source facts, not the derived answer.
   Examples:
   - quick ratio: current assets, inventory, current liabilities, or the explicitly
     requested quick-asset components
   - inventory turnover: cost of sales, beginning inventory, ending inventory
   - EBITDA: operating income, depreciation and amortization, revenue and/or capex
   - largest balance-sheet item: the complete relevant statement section
8. For SEC registration or exchange-listing questions, query the title-page heading
   "Securities registered pursuant to Section 12(b)" and require the complete list.
   A negative or "none" answer always requires an authoritative complete list or an
   explicit absence statement; ordinary related passages cannot prove absence.
9. Preserve the wording of requested operating metrics such as wages as a percent
   of sales. When the metric is discussed narratively rather than as a statement
   line item, select chunk as well as table.
10. Return JSON only, matching this shape:
{
  "intent": "narrative_fact|numeric_lookup|comparison|financial_calculation|broad_summary",
  "scope": {
    "company": "string or null",
    "fiscal_years": [2022],
    "quarter": null,
    "document_types": []
  },
  "tools": ["chunk", "table"],
  "evidence_slots": [
    {
      "name": "short identifier",
      "description": "what evidence is required",
      "preferred_tool": "chunk|table|structured|calculator",
      "query": "focused semantic retrieval query"
    }
  ],
  "queries": {
    "chunk": ["focused narrative query"],
    "table": ["focused table row query"],
    "structured": ["metric name and entity"]
  },
  "requires_calculation": false
}

Question:
{question}
"""


class RetrievalPlanner(Protocol):
    def plan(self, question: str) -> RetrievalPlan: ...


def parse_plan_response(text: str) -> RetrievalPlan:
    decoder = json.JSONDecoder()
    start = text.find("{")
    if start < 0:
        raise ValueError("Planner response did not contain a JSON object.")
    payload, _end = decoder.raw_decode(text[start:])
    return RetrievalPlan.model_validate(payload)


class LLMRetrievalPlanner:
    def __init__(self, llm=None) -> None:
        self.llm = llm
        self.cache: dict[str, RetrievalPlan] = {}

    def plan(self, question: str) -> RetrievalPlan:
        if question in self.cache:
            return self.cache[question].model_copy(deep=True)
        try:
            llm = self.llm or Settings.llm
            prompt = PLANNER_PROMPT.replace("{question}", question)
            try:
                response = llm.complete(prompt, temperature=0)
            except TypeError:
                response = llm.complete(prompt)
            plan = parse_plan_response(str(response))
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:200]
            plan = RetrievalPlan.fallback(question, error=error)
        self.cache[question] = plan
        return plan.model_copy(deep=True)


class ReplayRetrievalPlanner:
    def __init__(self, plans: dict[str, RetrievalPlan]) -> None:
        self.plans = plans

    def plan(self, question: str) -> RetrievalPlan:
        plan = self.plans.get(question)
        if plan is None:
            return RetrievalPlan.fallback(
                question,
                error="Missing replay plan.",
            )
        return plan.model_copy(deep=True)
