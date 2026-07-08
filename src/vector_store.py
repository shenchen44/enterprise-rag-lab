import os

import chromadb
from llama_index.vector_stores.chroma import ChromaVectorStore


CHROMA_DB_DIR = os.getenv("CHROMA_DB_DIR", "src/chroma_db")
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "enterprise_rag_lab")
PAGE_CHROMA_COLLECTION = os.getenv("PAGE_CHROMA_COLLECTION", f"{CHROMA_COLLECTION}_pages")
TABLE_CHROMA_COLLECTION = os.getenv("TABLE_CHROMA_COLLECTION", f"{CHROMA_COLLECTION}_tables")


def get_chroma_collection(reset: bool = False):
    """Return the persistent Chroma collection used by the RAG index."""
    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    if reset:
        try:
            client.delete_collection(CHROMA_COLLECTION)
        except Exception:
            pass
    return client.get_or_create_collection(CHROMA_COLLECTION)


def get_page_chroma_collection(reset: bool = False):
    """Return the persistent Chroma collection used by page-level retrieval."""
    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    if reset:
        try:
            client.delete_collection(PAGE_CHROMA_COLLECTION)
        except Exception:
            pass
    return client.get_or_create_collection(PAGE_CHROMA_COLLECTION)


def get_table_chroma_collection(reset: bool = False):
    """Return the persistent Chroma collection used by table-aware retrieval."""
    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    if reset:
        try:
            client.delete_collection(TABLE_CHROMA_COLLECTION)
        except Exception:
            pass
    return client.get_or_create_collection(TABLE_CHROMA_COLLECTION)


def get_vector_store(reset: bool = False) -> ChromaVectorStore:
    """Create a LlamaIndex vector store backed by a real Chroma collection."""
    collection = get_chroma_collection(reset=reset)
    return ChromaVectorStore(chroma_collection=collection)
