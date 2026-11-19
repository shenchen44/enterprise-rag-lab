import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

ENV_PATH = Path(__file__).resolve().parent / ".env"


def generate_index():
    """
    Index the documents in the data directory.
    """
    from src.index import STORAGE_DIR
    from src.ingestion.pipeline import run_ingestion
    from src.settings import init_settings
    from src.vector_store import CHROMA_COLLECTION, CHROMA_DB_DIR, get_vector_store
    from llama_index.core.indices import (
        VectorStoreIndex,
    )
    from llama_index.core.storage import StorageContext

    load_dotenv(ENV_PATH)
    init_settings()

    logger.info("Creating new Chroma-backed index")
    data_dir = os.environ.get("DATA_DIR", "ui/data")
    chunk_size = int(os.environ.get("CHUNK_SIZE", "384"))
    chunk_overlap = int(os.environ.get("CHUNK_OVERLAP", "64"))
    parent_chunk_size = int(os.environ.get("PARENT_CHUNK_SIZE", "1024"))
    parent_chunk_overlap = int(os.environ.get("PARENT_CHUNK_OVERLAP", "120"))
    nodes = run_ingestion(
        data_dir,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        parent_chunk_size=parent_chunk_size,
        parent_chunk_overlap=parent_chunk_overlap,
    )
    vector_store = get_vector_store(reset=True)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex(
        nodes,
        storage_context=storage_context,
        show_progress=True,
    )

    # Store docstore/index metadata locally. Embeddings and chunk payloads live
    # in the persistent Chroma collection.
    index.storage_context.persist(STORAGE_DIR)
    logger.info(
        "Finished creating new index. chunks=%s Chroma path=%s collection=%s metadata=%s",
        len(nodes),
        CHROMA_DB_DIR,
        CHROMA_COLLECTION,
        STORAGE_DIR,
    )
