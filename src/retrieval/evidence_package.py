from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from src.retrieval.plan_schema import EvidenceSlot, RetrievalPlan, RetrievalTool
from src.retrieval.tokenizer import tokenize
from src.retrieval.types import RetrievalHit


class SlotStatus(str, Enum):
    FILLED = "filled"
    MISSING = "missing"
    CONFLICTING = "conflicting"


class EvidenceDecision(str, Enum):
    ANSWERED = "answered"
    QUALIFIED = "qualified"
    CONFLICT = "conflict"
    INSUFFICIENT = "insufficient"


class SlotAssessment(BaseModel):
    name: str
    description: str
    preferred_tool: RetrievalTool
    status: SlotStatus
    citation_ids: list[str] = Field(default_factory=list)
    note: str = ""


class EvidencePackage(BaseModel):
    decision: EvidenceDecision
    completeness: float = Field(ge=0, le=1)
    slots: list[SlotAssessment]
    missing_slots: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


def _compatible(slot: EvidenceSlot, hit: RetrievalHit) -> bool:
    granularity = str(hit.metadata.get("retrieval_granularity") or "")
    if slot.preferred_tool == RetrievalTool.CHUNK:
        return granularity in {"child_chunk", "parent_chunk", "chunk", ""}
    if slot.preferred_tool == RetrievalTool.TABLE:
        return granularity in {"table", "table_row"}
    if slot.preferred_tool == RetrievalTool.STRUCTURED:
        return granularity == "structured_record"
    if slot.preferred_tool == RetrievalTool.CALCULATOR:
        return granularity == "calculation"
    return False


def _slot_score(slot: EvidenceSlot, hit: RetrievalHit) -> tuple[float, float]:
    query_terms = set(tokenize(f"{slot.description} {slot.query}"))
    hit_terms = set(tokenize(hit.text))
    overlap = len(query_terms & hit_terms) / max(len(query_terms), 1)
    return overlap, hit.score


def _structured_conflict(hits: list[RetrievalHit]) -> str:
    values_by_metric: dict[str, set[str]] = {}
    for hit in hits:
        if hit.metadata.get("retrieval_granularity") != "structured_record":
            continue
        metric = str(hit.metadata.get("metric") or "").strip().lower()
        value = str(hit.metadata.get("value") or "").strip()
        if metric and value:
            values_by_metric.setdefault(metric, set()).add(value)
    conflicts = [
        f"Structured source returned different values for {metric}: {sorted(values)}"
        for metric, values in values_by_metric.items()
        if len(values) > 1
    ]
    return "; ".join(conflicts)


def _metadata_conflict(plan: RetrievalPlan, hits: list[RetrievalHit]) -> str:
    fields = {
        "company": ("company_key", bool(plan.scope.company)),
        "fiscal period": ("fiscal_year", len(plan.scope.fiscal_years) == 1),
        "quarter": ("quarter", plan.scope.quarter is not None),
        "document version": ("document_version", True),
        "unit": ("unit", True),
    }
    messages: list[str] = []
    for label, (key, should_check) in fields.items():
        if not should_check:
            continue
        values = {
            str(hit.metadata[key]).strip().lower()
            for hit in hits
            if hit.metadata.get(key) not in (None, "")
        }
        if len(values) > 1:
            messages.append(f"incompatible {label}: {sorted(values)}")
    return "; ".join(messages)


def assemble_evidence_package(
    plan: RetrievalPlan,
    hits: list[RetrievalHit],
) -> EvidencePackage:
    fallback_tool = next(
        (
            tool
            for tool in plan.tools
            if tool != RetrievalTool.CALCULATOR
        ),
        RetrievalTool.CHUNK,
    )
    slots = plan.evidence_slots or [
        EvidenceSlot(
            name="answer_evidence",
            description="Evidence directly supporting the requested answer.",
            preferred_tool=fallback_tool,
            query="answer evidence",
        )
    ]
    assessments: list[SlotAssessment] = []
    conflicts: list[str] = []
    has_explicit_assignments = any(
        hit.metadata.get("evidence_slot_names") for hit in hits
    )
    for slot in slots:
        candidates = [
            hit
            for hit in hits
            if _compatible(slot, hit)
            and (
                slot.name in (hit.metadata.get("evidence_slot_names") or [])
                if has_explicit_assignments
                else True
            )
        ]
        ranked = sorted(
            candidates,
            key=lambda hit: _slot_score(slot, hit),
            reverse=True,
        )
        selected = ranked[:2]
        conflict = "; ".join(
            value
            for value in (
                _structured_conflict(selected),
                _metadata_conflict(plan, selected),
            )
            if value
        )
        if conflict:
            conflicts.append(f"{slot.name}: {conflict}")
            status = SlotStatus.CONFLICTING
        elif selected:
            status = SlotStatus.FILLED
        else:
            status = SlotStatus.MISSING
        assessments.append(
            SlotAssessment(
                name=slot.name,
                description=slot.description,
                preferred_tool=slot.preferred_tool,
                status=status,
                citation_ids=[hit.citation_id for hit in selected],
                note=conflict,
            )
        )

    filled_count = sum(
        assessment.status == SlotStatus.FILLED for assessment in assessments
    )
    missing = [
        assessment.name
        for assessment in assessments
        if assessment.status == SlotStatus.MISSING
    ]
    completeness = filled_count / max(len(assessments), 1)
    if conflicts:
        decision = EvidenceDecision.CONFLICT
    elif filled_count == len(assessments):
        decision = EvidenceDecision.ANSWERED
    elif filled_count == 0:
        decision = EvidenceDecision.INSUFFICIENT
    else:
        decision = EvidenceDecision.QUALIFIED
    return EvidencePackage(
        decision=decision,
        completeness=completeness,
        slots=assessments,
        missing_slots=missing,
        conflicts=conflicts,
    )


def aggregate_evidence_packages(rows: list[dict]) -> dict:
    packages = [row["evidence_package"] for row in rows if row.get("evidence_package")]
    counts = {decision.value: 0 for decision in EvidenceDecision}
    for package in packages:
        counts[str(package.get("decision", ""))] = (
            counts.get(str(package.get("decision", "")), 0) + 1
        )
    return {
        "evaluated_cases": len(packages),
        "average_completeness": (
            sum(float(package.get("completeness", 0)) for package in packages)
            / len(packages)
            if packages
            else None
        ),
        "fully_answered_rate": (
            counts[EvidenceDecision.ANSWERED.value] / len(packages)
            if packages
            else None
        ),
        "decision_counts": counts,
        "missing_slot_count": sum(
            len(package.get("missing_slots", [])) for package in packages
        ),
        "conflict_case_count": counts[EvidenceDecision.CONFLICT.value],
    }
