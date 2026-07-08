import logging
import os

from llama_index.core.indices import VectorStoreIndex, load_index_from_storage
from llama_index.core.storage import StorageContext

from src.vector_store import CHROMA_COLLECTION, CHROMA_DB_DIR, get_chroma_collection, get_vector_store

logger = logging.getLogger("uvicorn")

STORAGE_DIR = "src/storage"


def get_index():
    vector_store = get_vector_store()
    collection = get_chroma_collection()
    if collection.count() > 0:
        logger.info(
            "Loading index from Chroma path=%s collection=%s count=%s",
            CHROMA_DB_DIR,
            CHROMA_COLLECTION,
            collection.count(),
        )
        return VectorStoreIndex.from_vector_store(vector_store)

    # Fallback for older local-storage indexes generated before Chroma support.
    if not os.path.exists(STORAGE_DIR):
        return None

    logger.info(f"Loading index from {STORAGE_DIR}...")
    storage_context = StorageContext.from_defaults(persist_dir=STORAGE_DIR)
    index = load_index_from_storage(storage_context)
    logger.info(f"Finished loading index from {STORAGE_DIR}")
    return index
