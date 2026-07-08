from dotenv import load_dotenv

from llama_index.core.agent.workflow import AgentWorkflow
from llama_index.core.settings import Settings

from src.index import get_index
from src.query import get_query_engine_tool
from src.settings import init_settings


def create_workflow() -> AgentWorkflow:
    load_dotenv()
    init_settings()
    index = get_index()
    if index is None:
        raise RuntimeError(
            "Index not found! Please run `uv run generate` to index the data first."
        )
    # Create a hybrid retrieval tool. The tool output already contains
    # citation markers in the format [citation:chunk_id].
    query_tool = get_query_engine_tool(index=index)

    # Define the system prompt for the agent
    # Append the citation system prompt to the system prompt
    system_prompt = """
You are a helpful enterprise RAG assistant.
Use the query_index tool to retrieve evidence before answering knowledge-base
questions. Preserve citation markers like [citation:chunk_id] exactly when
using facts from retrieved evidence. If the evidence is insufficient, say so.
"""

    return AgentWorkflow.from_tools_or_functions(
        tools_or_functions=[query_tool],
        llm=Settings.llm,
        system_prompt=system_prompt,
    )


workflow = create_workflow()
