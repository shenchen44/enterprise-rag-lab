from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.retrieval.plan_schema import RetrievalScope
from src.retrieval.source_period import normalize_company_key


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    return tuple(
        value.strip()
        for value in os.getenv(name, default).split(",")
        if value.strip()
    )


@dataclass(frozen=True, slots=True)
class RetrievalRequest:
    """Identity and time boundary supplied by the application, never the LLM."""

    tenant_id: str = "default"
    principal_id: str = "anonymous"
    acl_scopes: tuple[str, ...] = ("public",)
    document_version: int | None = 1
    as_of_epoch: int = field(
        default_factory=lambda: int(datetime.now(timezone.utc).timestamp())
    )

    @classmethod
    def from_env(cls) -> "RetrievalRequest":
        return cls(
            tenant_id=os.getenv("RAG_TENANT_ID", "default"),
            principal_id=os.getenv("RAG_PRINCIPAL_ID", "anonymous"),
            acl_scopes=_csv_env("RAG_ACL_SCOPES", "public"),
            document_version=int(os.getenv("RAG_DOCUMENT_VERSION", "1")),
        )


@dataclass(frozen=True, slots=True)
class RetrievalFilter:
    tenant_id: str
    acl_scopes: tuple[str, ...]
    company_key: str = ""
    fiscal_years: tuple[int, ...] = ()
    quarter: int | None = None
    document_types: tuple[str, ...] = ()
    document_version: int | None = None
    as_of_epoch: int | None = None

    @classmethod
    def from_request_and_scope(
        cls,
        request: RetrievalRequest,
        scope: RetrievalScope,
    ) -> "RetrievalFilter":
        return cls(
            tenant_id=request.tenant_id,
            acl_scopes=request.acl_scopes,
            company_key=normalize_company_key(scope.company),
            fiscal_years=tuple(scope.fiscal_years),
            quarter=scope.quarter,
            document_types=tuple(
                value.lower().replace("-", "") for value in scope.document_types
            ),
            document_version=request.document_version,
            as_of_epoch=request.as_of_epoch,
        )

    def chroma_where(self, *, granularity: str | None = None) -> dict:
        clauses: list[dict] = [
            {"tenant_id": {"$eq": self.tenant_id}},
            {"acl_scope": {"$in": list(self.acl_scopes)}},
        ]
        if self.company_key:
            clauses.append({"company_key": {"$eq": self.company_key}})
        if self.fiscal_years:
            clauses.append({"fiscal_year": {"$in": list(self.fiscal_years)}})
        if self.quarter is not None:
            clauses.append({"quarter": {"$eq": self.quarter}})
        if self.document_types:
            clauses.append({"form_type": {"$in": list(self.document_types)}})
        if self.document_version is not None:
            clauses.append({"document_version": {"$eq": self.document_version}})
        if granularity:
            clauses.append({"retrieval_granularity": {"$eq": granularity}})
        return clauses[0] if len(clauses) == 1 else {"$and": clauses}

    def matches(self, metadata: dict, *, granularity: str | None = None) -> bool:
        if str(metadata.get("tenant_id", "")) != self.tenant_id:
            return False
        if str(metadata.get("acl_scope", "")) not in self.acl_scopes:
            return False
        if granularity and metadata.get("retrieval_granularity") != granularity:
            return False
        if self.company_key and metadata.get("company_key") != self.company_key:
            return False
        if self.fiscal_years and metadata.get("fiscal_year") not in self.fiscal_years:
            return False
        if self.quarter is not None and metadata.get("quarter") != self.quarter:
            return False
        if self.document_types and metadata.get("form_type") not in self.document_types:
            return False
        if (
            self.document_version is not None
            and metadata.get("document_version") != self.document_version
        ):
            return False
        valid_from = int(metadata.get("valid_from_epoch", 0) or 0)
        valid_to = int(metadata.get("valid_to_epoch", 0) or 0)
        if self.as_of_epoch is not None:
            if valid_from and valid_from > self.as_of_epoch:
                return False
            if valid_to and valid_to <= self.as_of_epoch:
                return False
        return True

    @property
    def has_relaxable_scope(self) -> bool:
        return bool(
            self.fiscal_years
            or self.quarter is not None
            or self.document_types
        )

    def without_period_and_document_type(self) -> "RetrievalFilter":
        """Keep security/entity boundaries while relaxing ambiguous report metadata."""
        return RetrievalFilter(
            tenant_id=self.tenant_id,
            acl_scopes=self.acl_scopes,
            company_key=self.company_key,
            document_version=self.document_version,
            as_of_epoch=self.as_of_epoch,
        )
