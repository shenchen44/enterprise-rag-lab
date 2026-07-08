from __future__ import annotations

from src.retrieval.types import RetrievalHit


def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievalHit]],
    *,
    top_k: int,
    rrf_k: int = 60,
) -> list[RetrievalHit]:
    fused: dict[str, RetrievalHit] = {}
    scores: dict[str, float] = {}
    debug_sources: dict[str, list[dict]] = {}

    for hits in ranked_lists:
        for rank, hit in enumerate(hits, start=1):
            node_id = hit.node_id
            scores[node_id] = scores.get(node_id, 0.0) + 1.0 / (rrf_k + rank)
            debug_sources.setdefault(node_id, []).append(
                {"source": hit.source, "rank": rank, "score": hit.score}
            )
            if node_id not in fused:
                fused[node_id] = hit

    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
    results: list[RetrievalHit] = []
    for rank, (node_id, score) in enumerate(ordered, start=1):
        hit = fused[node_id]
        hit.score = score
        hit.source = "hybrid_rrf"
        hit.rank = rank
        hit.debug["fusion_sources"] = debug_sources.get(node_id, [])
        results.append(hit)
    return results

