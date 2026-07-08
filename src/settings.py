import os

from llama_index.core import Settings
from llama_index.core.base.llms.types import LLMMetadata
from llama_index.embeddings.fastembed import FastEmbedEmbedding
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI


class DeepSeekOpenAI(OpenAI):
    """OpenAI-compatible DeepSeek client with explicit metadata for LlamaIndex."""

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            context_window=int(os.getenv("LLM_CONTEXT_WINDOW", "64000")),
            num_output=int(os.getenv("LLM_NUM_OUTPUT", "4096")),
            is_chat_model=True,
            is_function_calling_model=False,
            model_name=self.model,
        )


def init_settings():
    """Initialize LLM and embedding settings.

    The generated template originally required OpenAI for both chat and
    embeddings. For learning RAG locally, we default to:

    - DeepSeek as an OpenAI-compatible LLM endpoint.
    - FastEmbed/BGE as the local embedding model.

    You can still switch back to OpenAI by changing LLM_PROVIDER and
    EMBEDDING_PROVIDER in src/.env.
    """
    llm_provider = os.getenv("LLM_PROVIDER", "deepseek").lower()
    embedding_provider = os.getenv("EMBEDDING_PROVIDER", "fastembed").lower()

    if llm_provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY is missing. Set it in src/.env before running."
            )
        Settings.llm = DeepSeekOpenAI(
            model=os.getenv("MODEL") or "deepseek-chat",
            api_key=api_key,
            api_base=os.getenv("OPENAI_BASE_URL") or "https://api.deepseek.com/v1",
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
            timeout=float(os.getenv("LLM_TIMEOUT", "90")),
        )
    elif llm_provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is missing. Set it in src/.env before running."
            )
        Settings.llm = OpenAI(
            model=os.getenv("MODEL") or "gpt-4.1",
            api_key=api_key,
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
            timeout=float(os.getenv("LLM_TIMEOUT", "90")),
        )
    else:
        raise RuntimeError(f"Unsupported LLM_PROVIDER: {llm_provider}")

    if embedding_provider == "fastembed":
        Settings.embed_model = FastEmbedEmbedding(
            model_name=os.getenv("EMBEDDING_MODEL") or "BAAI/bge-small-zh-v1.5"
        )
    elif embedding_provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is missing for OpenAI embeddings. Set it in src/.env."
            )
        Settings.embed_model = OpenAIEmbedding(
            model=os.getenv("EMBEDDING_MODEL") or "text-embedding-3-small",
            api_key=api_key,
        )
    else:
        raise RuntimeError(f"Unsupported EMBEDDING_PROVIDER: {embedding_provider}")
