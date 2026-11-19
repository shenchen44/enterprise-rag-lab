from __future__ import annotations

import re
from statistics import mean
from typing import Iterable

from src.retrieval.types import RetrievalHit


STOPWORDS = {
    "about",
    "above",
    "after",
    "again",
    "against",
    "also",
    "amount",
    "answer",
    "between",
    "below",
    "based",
    "because",
    "before",
    "being",
    "company",
    "could",
    "defined",
    "details",
    "does",
    "during",
    "from",
    "have",
    "into",
    "more",
    "most",
    "million",
    "primarily",
    "provided",
    "question",
    "ratio",
    "relevant",
    "should",
    "state",
    "than",
    "that",
    "their",
    "there",
    "these",
    "this",
    "through",
    "under",
    "using",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
    "year",
}


def normalize_source(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def source_value(metadata: dict) -> str:
    return str(
        metadata.get("source_path")
        or metadata.get("file_path")
        or metadata.get("file_name")
        or metadata.get("filename")
        or ""
    )


def source_matches(metadata: dict, expected_sources: Iterable[str]) -> bool:
    source = normalize_source(source_value(metadata))
    if not source:
        return False
    return any(normalize_source(expected) in source for expected in expected_sources)


def _int_from_value(value: object) -> int | None:
    if value is None:
        return None
    match = re.search(r"\d+", str(value))
    if not match:
        return None
    return int(match.group(0))


def page_numbers(metadata: dict) -> set[int]:
    numbers: set[int] = set()
    for key in ("page_number", "page_label", "page", "page_index"):
        number = _int_from_value(metadata.get(key))
        if number is None:
            continue
        numbers.add(number)
        if key == "page_index":
            numbers.add(number + 1)
    return numbers


def page_matches(metadata: dict, expected_pages: Iterable[int]) -> bool:
    expected = {int(page) for page in expected_pages if page is not None}
    if not expected:
        return False
    candidates = page_numbers(metadata)
    if not candidates:
        return False

    # FinanceBench evidence pages are commonly zero-based, while PDF extraction
    # libraries usually expose one-based page labels. Accept both conventions.
    normalized_expected = expected | {page + 1 for page in expected}
    return bool(candidates & normalized_expected)


def matched_expected_pages(metadata: dict, expected_pages: Iterable[int]) -> set[int]:
    expected = {int(page) for page in expected_pages if page is not None}
    candidates = page_numbers(metadata)
    matched: set[int] = set()
    for page in expected:
        if page in candidates or page + 1 in candidates:
            matched.add(page)
    return matched


def content_terms(*texts: str | None, limit: int = 30) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for text in texts:
        for term in re.findall(r"[a-zA-Z][a-zA-Z0-9&%-]{3,}|\$?-?\d[\d,]*(?:\.\d+)?%?", text or ""):
            normalized = term.lower().strip("$,%-")
            normalized = normalized.replace(",", "")
            if re.fullmatch(r"-?\d+\.0+", normalized):
                normalized = normalized.split(".", 1)[0]
            if not normalized or normalized in STOPWORDS or normalized in seen:
                continue
            if normalized.isdigit() and (len(normalized) < 2 or normalized.startswith(("19", "20"))):
                continue
            seen.add(normalized)
            terms.append(normalized)
            if len(terms) >= limit:
                return terms
    return terms


def term_recall(terms: list[str], text: str) -> tuple[float | None, list[str]]:
    if not terms:
        return None, []
    normalized_text = text.lower()
    compact_text = normalized_text.replace(",", "").replace("$", "")
    matched = [term for term in terms if term in normalized_text or term in compact_text]
    return len(matched) / len(terms), matched


def first_rank_for_source(hits: list[RetrievalHit], expected_sources: list[str]) -> int | None:
    for rank, hit in enumerate(hits, start=1):
        if source_matches(hit.metadata, expected_sources):
            return rank
    return None


def first_rank_for_page(hits: list[RetrievalHit], expected_sources: list[str], expected_pages: list[int]) -> int | None:
    if not expected_pages:
        return None
    for rank, hit in enumerate(hits, start=1):
        if source_matches(hit.metadata, expected_sources) and page_matches(hit.metadata, expected_pages):
            return rank
    return None


def retrieval_metrics_for_hits(item: dict, hits: list[RetrievalHit]) -> dict:
    expected_sources = item.get("expected_sources", [])
    expected_pages = item.get("expected_pages", [])
    reference_terms = content_terms(item.get("reference_answer"), item.get("reference_justification"))
    retrieved_text = "\n".join(hit.text for hit in hits)
    lexical_coverage, matched_terms = term_recall(reference_terms, retrieved_text)

    source_rank = first_rank_for_source(hits, expected_sources)
    page_rank = first_rank_for_page(hits, expected_sources, expected_pages)

    covered_pages: set[int] = set()
    for hit in hits:
        if source_matches(hit.metadata, expected_sources):
            covered_pages.update(matched_expected_pages(hit.metadata, expected_pages))

    expected_page_count = len({int(page) for page in expected_pages if page is not None})
    page_recall = len(covered_pages) / expected_page_count if expected_page_count else None

    return {
        "source_hit": source_rank is not None,
        "source_first_rank": source_rank,
        "source_reciprocal_rank": 1.0 / source_rank if source_rank else 0.0,
        "page_hit": page_rank is not None if expected_pages else None,
        "page_first_rank": page_rank,
        "page_reciprocal_rank": 1.0 / page_rank if page_rank else (0.0 if expected_pages else None),
        "expected_page_recall": page_recall,
        "expected_pages_covered": sorted(covered_pages),
        "lexical_reference_coverage": lexical_coverage,
        "reference_terms": reference_terms,
        "matched_reference_terms": matched_terms,
    }


def _average(values: Iterable[float | int | None]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return mean(clean) if clean else None


def _percentile(values: Iterable[float | int | None], percentile: float) -> float | None:
    clean = sorted(float(value) for value in values if value is not None)
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    index = (len(clean) - 1) * percentile
    lower = int(index)
    upper = min(lower + 1, len(clean) - 1)
    weight = index - lower
    return clean[lower] * (1 - weight) + clean[upper] * weight


def _rate(values: Iterable[bool | None]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return sum(1 for value in clean if value) / len(clean)


def aggregate_retrieval_rows(rows: list[dict]) -> dict:
    metrics = [row["retrieval_metrics"] for row in rows if row.get("retrieval_metrics")]
    return {
        "source_hit_rate": _rate(metric.get("source_hit") for metric in metrics),
        "source_mrr": _average(metric.get("source_reciprocal_rank") for metric in metrics),
        "page_hit_rate": _rate(metric.get("page_hit") for metric in metrics),
        "page_mrr": _average(metric.get("page_reciprocal_rank") for metric in metrics),
        "expected_page_recall": _average(metric.get("expected_page_recall") for metric in metrics),
        "lexical_reference_coverage": _average(
            metric.get("lexical_reference_coverage") for metric in metrics
        ),
    }


def chunk_char_lengths(records: list[dict]) -> list[int]:
    return [len(record.get("text") or "") for record in records]


def has_page_metadata(record: dict) -> bool:
    return bool(page_numbers(record.get("metadata") or {}))


def global_chunk_profile(records: list[dict]) -> dict:
    lengths = chunk_char_lengths(records)
    return {
        "avg_chunk_chars": _average(lengths),
        "median_chunk_chars": _percentile(lengths, 0.5),
        "p90_chunk_chars": _percentile(lengths, 0.9),
        "empty_chunk_ratio": _rate((length == 0 for length in lengths)),
        "page_metadata_coverage": _rate(has_page_metadata(record) for record in records),
    }


def chunking_metrics_for_question(item: dict, records: list[dict]) -> dict:
    expected_sources = item.get("expected_sources", [])
    expected_pages = item.get("expected_pages", [])
    source_records = [
        record for record in records if source_matches(record.get("metadata") or {}, expected_sources)
    ]
    evidence_records = [
        record
        for record in source_records
        if page_matches(record.get("metadata") or {}, expected_pages)
    ]

    expected_page_set = {int(page) for page in expected_pages if page is not None}
    covered_pages: set[int] = set()
    for record in evidence_records:
        covered_pages.update(matched_expected_pages(record.get("metadata") or {}, expected_pages))

    return {
        "source_chunk_count": len(source_records),
        "evidence_chunk_count": len(evidence_records),
        "expected_page_coverage": (
            len(covered_pages) / len(expected_page_set) if expected_page_set else None
        ),
        "expected_pages_covered": sorted(covered_pages),
    }


def evaluate_chunking(records: list[dict], questions: list[dict]) -> dict:
    rows = [
        {
            "question": item.get("question"),
            "expected_sources": item.get("expected_sources", []),
            "expected_pages": item.get("expected_pages", []),
            "chunking_metrics": chunking_metrics_for_question(item, records),
        }
        for item in questions
    ]
    metrics = [row["chunking_metrics"] for row in rows]
    global_profile = global_chunk_profile(records)
    return {
        "chunk_count": len(records),
        "questions": len(questions),
        "source_chunk_coverage": _rate(metric["source_chunk_count"] > 0 for metric in metrics),
        "evidence_page_coverage": _average(metric.get("expected_page_coverage") for metric in metrics),
        **global_profile,
        "rows": rows,
    }
