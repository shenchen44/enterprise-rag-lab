from llama_index.core.schema import Document

from src.ingestion.pipeline import build_hierarchical_nodes


def test_hierarchical_ingestion_indexes_children_and_keeps_complete_parents() -> None:
    document = Document(
        text=" ".join(f"token{i}" for i in range(240)),
        metadata={
            "source_path": "ACME_2023_10K.pdf",
            "page_number": 7,
            "doc_id": "doc-1",
        },
    )

    parents, children = build_hierarchical_nodes(
        [document],
        parent_chunk_size=100,
        parent_chunk_overlap=10,
        child_chunk_size=30,
        child_chunk_overlap=5,
    )

    parent_ids = {record["id"] for record in parents}
    assert len(parents) > 1
    assert len(children) > len(parents)
    assert all(child.metadata["parent_id"] in parent_ids for child in children)
    assert all(
        child.metadata["retrieval_granularity"] == "child_chunk"
        for child in children
    )
    assert all(
        record["metadata"]["retrieval_granularity"] == "parent_chunk"
        for record in parents
    )
    assert all(record["metadata"]["page_number"] == 7 for record in parents)


def test_parent_chunk_must_be_larger_than_child_chunk() -> None:
    document = Document(text="short document", metadata={"source_path": "a.pdf"})

    try:
        build_hierarchical_nodes(
            [document],
            parent_chunk_size=100,
            parent_chunk_overlap=10,
            child_chunk_size=100,
            child_chunk_overlap=10,
        )
    except ValueError as exc:
        assert "greater than child_chunk_size" in str(exc)
    else:
        raise AssertionError("Expected invalid hierarchy sizes to fail")
