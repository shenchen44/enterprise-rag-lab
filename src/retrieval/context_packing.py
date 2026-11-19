"""Structure-aware context assembly for financial RAG generation.

Child chunks are useful retrieval keys, but they are often too small to carry a
complete financial claim. This module expands selected children to their complete
parent chunks or parent tables, then packs diverse evidence units into a bounded
generation context.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from src.retrieval.source_period import parse_query_scope, parse_source_profile, route_score
from src.retrieval.types import RetrievalHit


FINANCE_TERMS = {
    "revenue",
    "income",
    "assets",
    "liabilities",
    "sales",
    "cash",
    "margin",
    "inventory",
    "debt",
    "tax",
    "segment",
    "expense",
    "benefit",
}

CONTEXT_CHAR_BUDGET = 20_000
CONTEXT_MAX_UNITS = 10


def source_key(metadata: dict) -> str:
    return str(metadata.get("source_path") or metadata.get("file_path") or metadata.get("file_name") or "")


def source_identity(metadata: dict) -> str:
    source = source_key(metadata)
    return Path(source).name.lower() if source else ""


def page_number(metadata: dict) -> int | None:
    for key in ("page_number", "page_label", "page", "page_index"):
        value = metadata.get(key)
        match = re.search(r"\d+", str(value)) if value is not None else None
        if match:
            number = int(match.group(0))
            return number + 1 if key == "page_index" else number
    return None


def tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z][a-z0-9&%-]*", text.lower())
        if len(token) > 2
    }


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def constrain_hits_by_metadata(question: str, hits: list[RetrievalHit]) -> list[RetrievalHit]:
    """Prefer evidence matching an explicit company, fiscal year, and filing type.

    A constraint is only applied when a matching candidate is already present. This
    avoids turning a recall miss into an empty context while preventing an FY 10-K
    question from mixing in a same-company 10-Q when an annual filing is available.
    """
    scope = parse_query_scope(question)
    if not hits or (not scope.company and not scope.fiscal_years and scope.quarter is None):
        return hits

    synthetic = [
        hit for hit in hits
        if hit.metadata.get("retrieval_granularity") == "calculation"
    ]
    constrained = [hit for hit in hits if hit not in synthetic]

    def apply_if_available(predicate) -> None:
        nonlocal constrained
        matches = [hit for hit in constrained if predicate(hit)]
        if matches:
            constrained = matches

    if scope.company:
        apply_if_available(lambda hit: parse_source_profile(hit.metadata).company == scope.company)
    if scope.fiscal_years:
        apply_if_available(lambda hit: parse_source_profile(hit.metadata).fiscal_year in scope.fiscal_years)
    if scope.quarter is not None:
        apply_if_available(lambda hit: parse_source_profile(hit.metadata).quarter == scope.quarter)
    elif scope.annual_requested:
        apply_if_available(lambda hit: parse_source_profile(hit.metadata).form_type == "10k")

    for rank, hit in enumerate(constrained, start=1):
        profile = parse_source_profile(hit.metadata)
        hit.rank = rank
        hit.debug["metadata_constraint_score"] = route_score(scope, profile)
        hit.debug["metadata_constraint_company"] = profile.company
        hit.debug["metadata_constraint_year"] = profile.fiscal_year
        hit.debug["metadata_constraint_form"] = profile.form_type
    return [*constrained, *synthetic]


def split_blocks(text: str) -> list[str]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n+", text) if block.strip()]
    if len(blocks) > 1:
        return blocks
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines if len(lines) > 1 else ([text.strip()] if text.strip() else [])


def select_structured_blocks(question: str, text: str, *, max_chars: int) -> str:
    """Select whole paragraph/line blocks and their neighbors, never sentences."""
    blocks = split_blocks(text)
    if not blocks:
        return ""
    if len(text) <= max_chars:
        return text.strip()

    query_terms = tokens(question)
    scored: list[tuple[float, int]] = []
    for index, block in enumerate(blocks):
        block_terms = tokens(block)
        score = float(len(query_terms & block_terms))
        if re.search(r"\d", block):
            score += 1.5
        if FINANCE_TERMS & block_terms:
            score += 0.8
        scored.append((score, index))

    selected_indices: set[int] = set()
    for _score, index in sorted(scored, key=lambda item: (-item[0], item[1]))[:3]:
        selected_indices.add(index)
        if index > 0:
            selected_indices.add(index - 1)
        if index + 1 < len(blocks):
            selected_indices.add(index + 1)

    chosen: list[str] = []
    used = 0
    for index in sorted(selected_indices):
        block = blocks[index]
        addition = len(block) + (2 if chosen else 0)
        if chosen and used + addition > max_chars:
            continue
        if not chosen and len(block) > max_chars:
            # Preserve line boundaries when a single PDF extraction block is huge.
            lines = [line for line in block.splitlines() if line.strip()]
            kept: list[str] = []
            for line in lines:
                if sum(len(value) + 1 for value in kept) + len(line) > max_chars:
                    break
                kept.append(line)
            chosen.append("\n".join(kept) if kept else block[:max_chars])
            break
        chosen.append(block)
        used += addition
    return "\n\n".join(chosen) if chosen else text[:max_chars]


def select_table_context(text: str, row_labels: set[str], *, max_chars: int) -> str:
    """Keep table preamble, header, matching rows, and adjacent rows as one unit."""
    if len(text) <= max_chars:
        return text.strip()
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    table_start = next((index for index, line in enumerate(lines) if line.lstrip().startswith("|")), None)
    if table_start is None:
        return select_structured_blocks(" ".join(row_labels), text, max_chars=max_chars)

    preamble = lines[:table_start]
    table_lines = lines[table_start:]
    header_end = min(2, len(table_lines))
    selected_indices: set[int] = set(range(header_end))
    normalized_labels = {label.lower() for label in row_labels if label}
    for index, line in enumerate(table_lines[header_end:], start=header_end):
        normalized = line.lower()
        if any(label in normalized for label in normalized_labels):
            selected_indices.add(index)
            if index + 1 < len(table_lines):
                selected_indices.add(index + 1)
            if index > header_end:
                selected_indices.add(index - 1)
    if len(selected_indices) == header_end:
        selected_indices.update(range(header_end, min(header_end + 4, len(table_lines))))

    output = [*preamble, *(table_lines[index] for index in sorted(selected_indices))]
    kept: list[str] = []
    used = 0
    for line in output:
        if used + len(line) + 1 > max_chars and kept:
            break
        kept.append(line)
        used += len(line) + 1
    return "\n".join(kept)


def make_parent_contexts(
    question: str,
    hits: list[RetrievalHit],
    *,
    parent_records: list[dict],
    table_retriever,
) -> list[RetrievalHit]:
    """Expand searchable children into complete chunk or table parents."""
    parents = {
        str(record["id"]): record
        for record in parent_records
        if record.get("id")
    }
    groups: dict[tuple[str, str, str], list[RetrievalHit]] = defaultdict(list)
    for hit in hits:
        metadata = hit.metadata
        granularity = str(metadata.get("retrieval_granularity") or "chunk")
        source = source_identity(metadata)
        table_id = str(metadata.get("table_id") or "")
        parent_id = str(metadata.get("parent_id") or "")
        if granularity == "table_row" and table_id:
            key = ("table", source, table_id)
        elif parent_id and parent_id in parents:
            key = ("parent_chunk", source, parent_id)
        else:
            key = ("child", source, hit.node_id)
        groups[key].append(hit)

    contexts: list[RetrievalHit] = []
    for (kind, source, parent_key), children in groups.items():
        best = max(children, key=lambda hit: hit.score)
        slot_names = sorted(
            {
                slot_name
                for child in children
                for slot_name in child.metadata.get("evidence_slot_names", [])
            }
        )
        retrieval_role = "slot_anchor" if slot_names else best.metadata.get(
            "retrieval_role",
            "child",
        )
        child_labels = {str(hit.metadata.get("row_label") or "") for hit in children}
        metadata = dict(best.metadata)
        parent_text = best.text
        parent_id = best.node_id
        max_chars = len(parent_text)

        if kind == "table":
            parent = table_retriever.parent_table(parent_key) if table_retriever is not None else None
            if parent:
                parent_text = select_table_context(parent["text"], child_labels, max_chars=6000)
                metadata = {
                    **parent["metadata"],
                    "parent_id": parent_key,
                    "parent_type": "table",
                }
                parent_id = parent["id"]
            else:
                parent_text = "\n\n".join(hit.text for hit in children)
                metadata.update({"parent_id": parent_key, "parent_type": "table_row_group"})
            max_chars = 6000
        elif kind == "parent_chunk":
            parent = parents[parent_key]
            parent_text = parent["text"]
            metadata = {
                **parent["metadata"],
                "parent_id": parent_key,
                "parent_type": "parent_chunk",
            }
            parent_id = parent["id"]
            max_chars = len(parent_text)
        else:
            parent_text = best.text
            metadata.update({"parent_id": best.node_id, "parent_type": "child"})

        metadata["retrieval_role"] = retrieval_role
        if slot_names:
            metadata["evidence_slot_names"] = slot_names
        metadata.setdefault("chunk_id", metadata.get("page_id") or metadata.get("table_id") or parent_id)
        contexts.append(
            RetrievalHit(
                node_id=parent_id,
                text=parent_text,
                metadata=metadata,
                score=best.score,
                source=f"{best.source}_parent_{kind}",
                rank=best.rank,
                debug={
                    **best.debug,
                    "parent_type": kind,
                    "parent_child_count": len(children),
                    "parent_context_max_chars": max_chars,
                },
            )
        )
    return contexts


def pack_contexts(question: str, hits: list[RetrievalHit]) -> list[RetrievalHit]:
    """Keep ranked child anchors, then fill the remaining budget with supplements."""
    if not hits:
        return []
    budget = CONTEXT_CHAR_BUDGET
    max_units = CONTEXT_MAX_UNITS
    query_terms = tokens(question)
    selected: list[RetrievalHit] = []
    selected_terms: list[set[str]] = []
    used = 0

    anchors = sorted(
        (
            hit
            for hit in hits
            if hit.metadata.get("retrieval_role") in {"slot_anchor", "child"}
        ),
        key=lambda hit: (
            0 if hit.metadata.get("retrieval_role") == "slot_anchor" else 1,
            hit.rank,
        ),
    )
    for hit in anchors:
        if len(selected) >= max_units:
            break
        length = len(hit.text)
        if selected and used + length > budget:
            continue
        selected.append(hit)
        selected_terms.append(tokens(hit.text))
        used += length

    candidates = [hit for hit in hits if hit not in selected]
    while candidates and len(selected) < max_units:
        def selection_score(hit: RetrievalHit) -> float:
            hit_terms = tokens(hit.text)
            relevance = hit.score + 0.04 * len(query_terms & hit_terms)
            novelty = max((jaccard(hit_terms, terms) for terms in selected_terms), default=0.0)
            # Prefer a compact local evidence unit when relevance is comparable.
            return relevance - 0.25 * novelty - 0.00004 * len(hit.text)

        best = max(candidates, key=selection_score)
        candidates.remove(best)
        length = len(best.text)
        if selected and used + length > budget:
            continue
        selected.append(best)
        selected_terms.append(tokens(best.text))
        used += length

    for rank, hit in enumerate(selected, start=1):
        hit.rank = rank
        hit.debug["context_pack_rank"] = rank
        hit.debug["context_pack_total_chars"] = used
    return selected


def build_generation_context(
    question: str,
    hits: list[RetrievalHit],
    *,
    parent_records: list[dict],
    table_retriever,
) -> list[RetrievalHit]:
    constrained = constrain_hits_by_metadata(question, hits)
    parents = make_parent_contexts(
        question,
        constrained,
        parent_records=parent_records,
        table_retriever=table_retriever,
    )
    return pack_contexts(question, parents)
