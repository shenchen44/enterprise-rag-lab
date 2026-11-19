from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Protocol

from src.retrieval.request_context import RetrievalFilter
from src.retrieval.tokenizer import tokenize
from src.retrieval.types import RetrievalHit


class StructuredDataProvider(Protocol):
    def search(
        self,
        query: str,
        *,
        retrieval_filter: RetrievalFilter,
        top_k: int,
    ) -> list[RetrievalHit]: ...


class EmptyStructuredDataProvider:
    def search(
        self,
        query: str,
        *,
        retrieval_filter: RetrievalFilter,
        top_k: int,
    ) -> list[RetrievalHit]:
        return []


class SqliteStructuredDataProvider:
    """Reference SQL adapter for dynamic facts; production API adapters share its contract."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def search(
        self,
        query: str,
        *,
        retrieval_filter: RetrievalFilter,
        top_k: int,
    ) -> list[RetrievalHit]:
        if not self.database_path.exists() or top_k <= 0:
            return []
        where = ["tenant_id = ?", f"acl_scope IN ({','.join('?' for _ in retrieval_filter.acl_scopes)})"]
        params: list[object] = [
            retrieval_filter.tenant_id,
            *retrieval_filter.acl_scopes,
        ]
        if retrieval_filter.company_key:
            where.append("company_key = ?")
            params.append(retrieval_filter.company_key)
        if retrieval_filter.fiscal_years:
            where.append(
                f"fiscal_year IN ({','.join('?' for _ in retrieval_filter.fiscal_years)})"
            )
            params.extend(retrieval_filter.fiscal_years)
        if retrieval_filter.quarter is not None:
            where.append("quarter = ?")
            params.append(retrieval_filter.quarter)
        if retrieval_filter.as_of_epoch is not None:
            where.append("(valid_from_epoch IS NULL OR valid_from_epoch <= ?)")
            where.append("(valid_to_epoch IS NULL OR valid_to_epoch > ?)")
            params.extend(
                [retrieval_filter.as_of_epoch, retrieval_filter.as_of_epoch]
            )
        sql = (
            "SELECT id, company_key, fiscal_year, quarter, metric, value, unit, "
            "source_system, observed_at, valid_from_epoch, valid_to_epoch, "
            "tenant_id, acl_scope FROM structured_facts WHERE "
            + " AND ".join(where)
            + " LIMIT 500"
        )
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(sql, params).fetchall()

        query_terms = set(tokenize(query))
        ranked: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            searchable = " ".join(
                str(row[key] or "")
                for key in ("company_key", "metric", "fiscal_year", "quarter")
            )
            terms = set(tokenize(searchable))
            score = len(query_terms & terms) / max(len(query_terms), 1)
            if score > 0:
                ranked.append((score, row))
        ranked.sort(key=lambda item: (item[0], str(item[1]["observed_at"] or "")), reverse=True)

        hits: list[RetrievalHit] = []
        for rank, (score, row) in enumerate(ranked[:top_k], start=1):
            metadata = dict(row)
            metadata.update(
                {
                    "retrieval_granularity": "structured_record",
                    "retrieval_role": "dynamic_fact",
                    "chunk_id": row["id"],
                }
            )
            text = (
                f"{row['metric']}: {row['value']} {row['unit'] or ''}".strip()
                + f"\nEntity: {row['company_key'] or 'unknown'}"
                + f"\nFiscal year: {row['fiscal_year'] or 'unknown'}"
                + f"\nSource system: {row['source_system'] or 'unknown'}"
                + f"\nObserved at: {row['observed_at'] or 'unknown'}"
            )
            hits.append(
                RetrievalHit(
                    node_id=str(row["id"]),
                    text=text,
                    metadata=metadata,
                    score=score,
                    source="structured_sql",
                    rank=rank,
                )
            )
        return hits


class StructuredDataGateway:
    def __init__(self, provider: StructuredDataProvider | None = None) -> None:
        if provider is not None:
            self.provider = provider
            return
        database_path = os.getenv("STRUCTURED_DATA_DB", "").strip()
        self.provider = (
            SqliteStructuredDataProvider(database_path)
            if database_path
            else EmptyStructuredDataProvider()
        )

    def search(
        self,
        query: str,
        *,
        retrieval_filter: RetrievalFilter,
        top_k: int,
    ) -> list[RetrievalHit]:
        return self.provider.search(
            query,
            retrieval_filter=retrieval_filter,
            top_k=top_k,
        )
