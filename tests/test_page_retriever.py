from src.retrieval.page_retriever import PageRetriever
from src.retrieval.types import RetrievalHit


def test_page_search_can_fuse_bm25_with_vector_hits(monkeypatch) -> None:
    retriever = PageRetriever.__new__(PageRetriever)
    vector_hit = RetrievalHit("vector", "Revenue was $100.", {}, 0.9, "page_vector", 1)
    bm25_hit = RetrievalHit("bm25", "Revenue fiscal 2022 was $100.", {}, 1.0, "bm25", 1)
    retriever.vector_search = lambda _query, *, top_k: [vector_hit]
    retriever.bm25 = type("BM25", (), {"search": lambda _self, _query, *, top_k: [bm25_hit]})()
    monkeypatch.setenv("PAGE_BM25_ENABLED", "true")

    hits = retriever.search("Revenue fiscal 2022", top_k=2)

    assert {hit.node_id for hit in hits} == {"vector", "bm25"}
