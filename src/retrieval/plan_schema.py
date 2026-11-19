from __future__ import annotations

from enum import Enum
import re

from pydantic import BaseModel, Field, ValidationInfo, field_validator


class RetrievalTool(str, Enum):
    CHUNK = "chunk"
    TABLE = "table"
    STRUCTURED = "structured"
    CALCULATOR = "calculator"


class RetrievalScope(BaseModel):
    company: str | None = None
    fiscal_years: list[int] = Field(default_factory=list, max_length=4)
    quarter: int | None = Field(default=None, ge=1, le=4)
    document_types: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("fiscal_years", mode="before")
    @classmethod
    def normalize_years(cls, value) -> list[int]:
        values = value if isinstance(value, list) else []
        years: list[int] = []
        for item in values:
            match = re.search(r"(?:19|20)\d{2}", str(item))
            if match:
                year = int(match.group(0))
                if year not in years:
                    years.append(year)
        return years[:4]

    @field_validator("quarter", mode="before")
    @classmethod
    def normalize_quarter(cls, value):
        if value is None:
            return None
        match = re.search(r"[1-4]", str(value))
        return int(match.group(0)) if match else None

    @field_validator("document_types", mode="before")
    @classmethod
    def limit_document_types(cls, value) -> list[str]:
        aliases = {
            "10-k": "10k",
            "10k": "10k",
            "annual report": "10k",
            "annual filing": "10k",
            "10-q": "10q",
            "10q": "10q",
            "quarterly report": "10q",
            "quarterly filing": "10q",
            "earnings": "earnings",
            "earnings release": "earnings",
        }
        normalized: list[str] = []
        for item in value if isinstance(value, list) else []:
            canonical = aliases.get(str(item).strip().lower())
            if canonical and canonical not in normalized:
                normalized.append(canonical)
        return normalized[:3]


class EvidenceSlot(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=240)
    preferred_tool: RetrievalTool
    query: str = Field(min_length=1, max_length=320)


class RetrievalQueries(BaseModel):
    chunk: list[str] = Field(default_factory=list, max_length=3)
    table: list[str] = Field(default_factory=list, max_length=4)
    structured: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("chunk", "table", "structured", mode="before")
    @classmethod
    def clean_queries(
        cls,
        values,
        info: ValidationInfo,
    ) -> list[str]:
        cleaned: list[str] = []
        for value in values if isinstance(values, list) else []:
            query = " ".join(value.split())
            if query and query not in cleaned:
                cleaned.append(query)
        limit = 3 if info.field_name == "chunk" else 4
        return cleaned[:limit]


class RetrievalPlan(BaseModel):
    intent: str = Field(min_length=1, max_length=80)
    scope: RetrievalScope = Field(default_factory=RetrievalScope)
    tools: list[RetrievalTool] = Field(min_length=1, max_length=4)
    evidence_slots: list[EvidenceSlot] = Field(default_factory=list, max_length=6)
    queries: RetrievalQueries = Field(default_factory=RetrievalQueries)
    requires_calculation: bool = False
    planner_status: str = "planned"
    planner_error: str | None = None

    @field_validator("tools")
    @classmethod
    def deduplicate_tools(cls, tools: list[RetrievalTool]) -> list[RetrievalTool]:
        return list(dict.fromkeys(tools))

    def uses(self, tool: RetrievalTool) -> bool:
        return tool in self.tools

    def queries_for(self, tool: RetrievalTool, original_question: str) -> list[str]:
        planned = list(getattr(self.queries, tool.value, []))
        planned.extend(
            slot.query
            for slot in self.evidence_slots
            if slot.preferred_tool == tool
        )
        return list(dict.fromkeys([original_question, *planned]))

    @classmethod
    def fallback(
        cls,
        question: str,
        *,
        error: str | None = None,
    ) -> "RetrievalPlan":
        return cls(
            intent="fallback_broad_retrieval",
            tools=[
                RetrievalTool.CHUNK,
                RetrievalTool.TABLE,
                RetrievalTool.STRUCTURED,
                RetrievalTool.CALCULATOR,
            ],
            evidence_slots=[
                EvidenceSlot(
                    name="answer_evidence",
                    description="Evidence directly supporting the requested answer.",
                    preferred_tool=RetrievalTool.CHUNK,
                    query=question,
                )
            ],
            planner_status="fallback",
            planner_error=error,
        )
