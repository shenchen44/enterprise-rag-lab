from __future__ import annotations

import re
import os
from dataclasses import dataclass
from pathlib import Path

from src.retrieval.types import RetrievalHit


COMPANY_ALIASES: dict[str, tuple[str, ...]] = {
    "3m": (r"\b3m\b",),
    "aes": (r"\baes\b", r"\baes corporation\b"),
    "amcor": (r"\bamcor\b",),
    "amd": (r"\bamd\b", r"\badvanced micro devices\b"),
    "americanexpress": (r"\bamerican express\b", r"\bamex\b"),
    "bestbuy": (r"\bbest buy\b",),
    "boeing": (r"\bboeing\b",),
    "pepsico": (r"\bpepsico\b", r"\bpepsi\b"),
    "ultabeauty": (r"\bulta\b", r"\bulta beauty\b"),
}


def normalize_company_key(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if not normalized:
        return ""
    for company, patterns in COMPANY_ALIASES.items():
        if any(re.search(pattern, normalized) for pattern in patterns):
            return company
    return re.sub(r"[^a-z0-9]+", "", normalized)


@dataclass(frozen=True, slots=True)
class SourceProfile:
    company: str = ""
    fiscal_year: int | None = None
    quarter: int | None = None
    form_type: str = ""


@dataclass(frozen=True, slots=True)
class QueryScope:
    company: str = ""
    fiscal_years: frozenset[int] = frozenset()
    quarter: int | None = None
    annual_requested: bool = False


def source_key(metadata: dict) -> str:
    return str(metadata.get("source_path") or metadata.get("file_path") or metadata.get("file_name") or "")


def source_stem(metadata: dict) -> str:
    source = source_key(metadata)
    return Path(source).stem.lower() if source else ""


def parse_source_profile(metadata: dict) -> SourceProfile:
    stem = source_stem(metadata)
    if not stem:
        return SourceProfile()

    compact = re.sub(r"[^a-z0-9]+", "", stem)
    company = ""
    for candidate in COMPANY_ALIASES:
        if compact.startswith(candidate):
            company = candidate
            break

    year_match = re.search(r"(?:19|20)\d{2}", stem)
    quarter_match = re.search(r"q([1-4])", stem, re.I)
    form_type = ""
    if "10k" in compact:
        form_type = "10k"
    elif "10q" in compact:
        form_type = "10q"
    elif "earnings" in compact:
        form_type = "earnings"

    return SourceProfile(
        company=company,
        fiscal_year=int(year_match.group(0)) if year_match else None,
        quarter=int(quarter_match.group(1)) if quarter_match else None,
        form_type=form_type,
    )


def governance_metadata(metadata: dict) -> dict:
    """Return scalar metadata used by all pre-retrieval access and scope filters."""
    profile = parse_source_profile(metadata)
    governed = {
        "tenant_id": str(metadata.get("tenant_id") or "default"),
        "acl_scope": str(metadata.get("acl_scope") or "public"),
        "document_version": int(metadata.get("document_version") or 1),
        "company_key": profile.company,
        "form_type": profile.form_type,
    }
    if profile.fiscal_year is not None:
        governed["fiscal_year"] = profile.fiscal_year
    if profile.quarter is not None:
        governed["quarter"] = profile.quarter
    for key in ("valid_from_epoch", "valid_to_epoch"):
        if metadata.get(key) is not None:
            governed[key] = int(metadata[key])
    return governed


def parse_query_scope(question: str) -> QueryScope:
    normalized = question.lower()
    company = ""
    for candidate, patterns in COMPANY_ALIASES.items():
        if any(re.search(pattern, normalized) for pattern in patterns):
            company = candidate
            break

    years: set[int] = set()
    for match in re.finditer(r"\bfy\s*([0-9]{2}|[0-9]{4})\b|\bfiscal year\s*((?:19|20)\d{2})\b", normalized):
        value = match.group(1) or match.group(2)
        year = int(value)
        years.add(2000 + year if year < 100 else year)
    for match in re.finditer(r"\b(?:as of|in|for|between|from|to)\s*((?:19|20)\d{2})\b", normalized):
        years.add(int(match.group(1)))

    quarter = None
    quarter_match = re.search(r"\bq([1-4])\b|quarter\s+([1-4])|([1-4])(?:st|nd|rd|th)\s+quarter", normalized)
    if quarter_match:
        quarter = int(next(group for group in quarter_match.groups() if group))

    annual_requested = bool(
        re.search(r"\bannual(?: report| filing)?\b|10-k|10k", normalized)
    ) and quarter is None

    return QueryScope(
        company=company,
        fiscal_years=frozenset(years),
        quarter=quarter,
        annual_requested=annual_requested,
    )


def route_score(scope: QueryScope, profile: SourceProfile) -> float:
    score = 0.0
    if scope.company:
        if profile.company == scope.company:
            score += 0.8
        elif profile.company:
            score -= 2.0

    if scope.fiscal_years and profile.fiscal_year is not None:
        if profile.fiscal_year in scope.fiscal_years:
            score += 0.45
        else:
            score -= 0.75

    if scope.quarter is not None and profile.quarter is not None:
        score += 0.35 if profile.quarter == scope.quarter else -0.5

    if scope.annual_requested:
        if profile.form_type == "10k":
            score += 0.25
        elif profile.form_type == "10q":
            score -= 0.6

    return score


def rerank_by_source_period(question: str, hits: list[RetrievalHit]) -> list[RetrievalHit]:
    scope = parse_query_scope(question)
    if not hits or (not scope.company and not scope.fiscal_years and scope.quarter is None):
        return hits

    routed_hits = hits
    if os.getenv("SOURCE_PERIOD_FILTER_ENABLED", "false").lower() == "true":
        company_filtered = hits
        if scope.company:
            matching_company = [
                hit
                for hit in hits
                if parse_source_profile(hit.metadata).company in {"", scope.company}
            ]
            if matching_company and len(matching_company) >= max(1, len(hits) // 3):
                company_filtered = matching_company

        routed_hits = company_filtered
        if scope.annual_requested and len(scope.fiscal_years) == 1:
            matching_year = [
                hit
                for hit in company_filtered
                if parse_source_profile(hit.metadata).fiscal_year in {None, next(iter(scope.fiscal_years))}
            ]
            if matching_year and len(matching_year) >= max(1, len(company_filtered) // 3):
                routed_hits = matching_year

    ranked = sorted(
        routed_hits,
        key=lambda hit: (route_score(scope, parse_source_profile(hit.metadata)), hit.score),
        reverse=True,
    )
    for rank, hit in enumerate(ranked, start=1):
        profile = parse_source_profile(hit.metadata)
        hit.rank = rank
        hit.debug["source_period_route_score"] = route_score(scope, profile)
        hit.debug["source_period_company"] = profile.company
        hit.debug["source_period_year"] = profile.fiscal_year
        hit.debug["source_period_quarter"] = profile.quarter
    return ranked
