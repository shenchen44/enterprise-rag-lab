from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class RetrievalHit:
    node_id: str
    text: str
    metadata: dict
    score: float
    source: str
    rank: int = 0
    debug: dict = field(default_factory=dict)

    @property
    def citation_id(self) -> str:
        return str(self.metadata.get("chunk_id") or self.node_id)

