from __future__ import annotations

import re

from src.retrieval.tokenizer import tokenize
from src.retrieval.types import RetrievalHit


CONCEPT_PATTERNS: dict[str, tuple[str, ...]] = {
    "operating_income": (
        r"\boperating income\b",
        r"\boperating profit\b",
        r"\bincome from operations\b",
    ),
    "capital_expenditures": (
        r"\bcapex\b",
        r"\bcapital expenditures?\b",
        r"\bcapital spending\b",
        r"\bpurchases? of (?:property,? plant and equipment|pp&e)\b",
    ),
    "depreciation_amortization": (
        r"\bdepreciation and amortization\b",
        r"\bdepreciation & amortization\b",
        r"\bd&a\b",
    ),
    "share_repurchases": (
        r"\bshare repurchases?\b",
        r"\bstock repurchases?\b",
        r"\brepurchase of (?:common )?stock\b",
    ),
    "wages": (
        r"\bwages?\b",
        r"\bpayroll\b",
        r"\blabor costs?\b",
    ),
    "revenue": (
        r"\bnet revenues?\b",
        r"\btotal revenues?\b",
        r"\bnet sales\b",
    ),
    "inventory": (
        r"\binventor(?:y|ies)\b",
    ),
    "current_assets": (
        r"\bcurrent assets\b",
    ),
    "current_liabilities": (
        r"\bcurrent liabilities\b",
    ),
    "cost_of_sales": (
        r"\bcost of (?:goods sold|sales|revenues?)\b",
    ),
    "operating_cash_flow": (
        r"\b(?:net )?cash (?:provided by|from) operating activities\b",
    ),
    "investing_cash_flow": (
        r"\b(?:net )?cash (?:provided by|used in|from) investing activities\b",
    ),
    "financing_cash_flow": (
        r"\b(?:net )?cash (?:provided by|used in|from) financing activities\b",
    ),
}

GENERIC_TERMS = {
    "company",
    "corporation",
    "financial",
    "fiscal",
    "flow",
    "from",
    "fy",
    "income",
    "million",
    "statement",
    "table",
    "total",
    "year",
}


def concepts(text: str) -> set[str]:
    normalized = text.lower()
    return {
        concept
        for concept, patterns in CONCEPT_PATTERNS.items()
        if any(re.search(pattern, normalized) for pattern in patterns)
    }


def query_quarter(text: str) -> str | None:
    normalized = text.lower()
    match = re.search(r"\bq([1-4])\b|\b([1-4])(?:st|nd|rd|th)\s+quarter\b", normalized)
    if match:
        return next(value for value in match.groups() if value)
    words = {
        "first quarter": "1",
        "second quarter": "2",
        "third quarter": "3",
        "fourth quarter": "4",
    }
    return next(
        (number for phrase, number in words.items() if phrase in normalized),
        None,
    )


def table_candidate_matches_slot(query: str, hit: RetrievalHit) -> bool:
    candidate_text = " ".join(
        [
            hit.text,
            str(hit.metadata.get("row_label") or ""),
            str(hit.metadata.get("surrounding_heading") or ""),
            str(hit.metadata.get("section_path") or ""),
        ]
    )
    required_concepts = concepts(query)
    candidate_concepts = concepts(candidate_text)
    if required_concepts and not (required_concepts & candidate_concepts):
        return False

    query_lower = query.lower()
    temporal_text = re.sub(
        r"^Source:.*$",
        "",
        candidate_text,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    candidate_lower = temporal_text.lower()
    quarter = query_quarter(query_lower)
    if quarter:
        quarter_signals = {
            f"q{quarter}",
            f"quarter {quarter}",
            f"{quarter}th quarter",
        }
        if quarter == "4":
            quarter_signals.add("13 weeks")
        if not any(signal in candidate_lower for signal in quarter_signals):
            return False

    if required_concepts:
        return True
    query_terms = {
        term
        for term in tokenize(query)
        if term not in GENERIC_TERMS and not re.fullmatch(r"(?:19|20)\d{2}", term)
    }
    candidate_terms = set(tokenize(candidate_text))
    return bool(query_terms & candidate_terms)
