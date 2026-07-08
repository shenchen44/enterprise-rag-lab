# Enterprise RAG Lab Study Guide

This project was generated with `create-llama` as a small, runnable LlamaIndex
Agentic RAG application. Use it as the base project for learning RAG internals
before extending it into an enterprise-style system.

## Current Project Shape

```text
ui/data/              Input documents. Put PDF, TXT, Markdown, DOCX files here.
src/generate.py       Ingestion entrypoint: load documents, chunk, embed, build index.
scripts/prepare_financebench.py  Builds a local FinanceBench subset.
src/vector_store.py   Chroma persistent vector database setup.
src/index.py          Loads the persisted Chroma-backed index.
src/query.py          Converts an index into a query engine and tool.
src/ingestion/        Explicit ingestion, chunking, metadata, and hash dedupe.
src/retrieval/        BM25, vector search, RRF hybrid fusion, and reranking.
src/eval/             Retrieval evaluation scripts and metrics.
src/citation.py       Adds citation ids to retrieved chunks and enforces cited answers.
src/workflow.py       Agentic RAG workflow: LLM agent + query tool + citation prompt.
src/settings.py       LLM and embedding model configuration.
llama_deploy.yml      Local deployment config for LlamaDeploy and the chat UI.
src/.env              Local environment variables. Put API keys here.
```

## Core RAG Concepts In This Template

## Dataset: FinanceBench

FinanceBench is the first recommended real dataset for this project. It contains
annual-report PDFs, financial analyst questions, reference answers, and evidence
pages. This makes it a good fit for studying enterprise RAG because the documents
are long, table-heavy, and require source-grounded answers.

Prepare the local subset:

```bash
git clone --depth 1 https://github.com/patronus-ai/financebench.git /private/tmp/financebench
uv run python scripts/prepare_financebench.py \
  --source /private/tmp/financebench \
  --doc-limit 5 \
  --question-limit 20
```

Generated files:

```text
ui/data/financebench/              selected annual-report PDFs
eval/financebench_questions.jsonl  retrieval evaluation questions
```

Scale-up path:

- `--doc-limit 5` to `20` or `50` to increase corpus size;
- `--question-limit 20` to `100+` for stronger evaluation;
- compare BM25-only, vector-only, hybrid, and reranked results;
- add answer-level evaluation after retrieval metrics are stable.

### 1. Ingestion Pipeline

File: `src/generate.py`

Current flow:

```text
ui/data
-> SimpleDirectoryReader
-> documents
-> chunk nodes
-> FastEmbed/BGE embeddings
-> Chroma collection
-> src/chroma_db
```

What to learn:

- how files are loaded;
- how documents become nodes/chunks;
- how embeddings are created;
- how the vector database persists embeddings and chunk payloads.
- how metadata and content hashes support dedupe and traceability.

### 2. Chunking

This project now uses explicit chunk settings in `src/ingestion/pipeline.py`.
It uses `TokenTextSplitter` so indexing does not depend on runtime NLTK corpus
downloads:

```python
from llama_index.core.node_parser import TokenTextSplitter

splitter = TokenTextSplitter(chunk_size=512, chunk_overlap=80)
nodes = splitter.get_nodes_from_documents(documents)
```

Tune these values in `src/.env`:

```env
CHUNK_SIZE=512
CHUNK_OVERLAP=80
```

### 3. Embedding

File: `src/settings.py`

Current default:

```text
FastEmbedEmbedding(BAAI/bge-small-zh-v1.5)
```

Enterprise extension:

- local embedding model, e.g. BGE;
- embedding dimension awareness;
- embedding cache;
- batch embedding for ingestion throughput.

### 4. Vector DB

Current vector database:

```text
Chroma persistent database under src/chroma_db
Collection: enterprise_rag_lab
```

The code path is:

```text
src/vector_store.py -> chromadb.PersistentClient -> ChromaVectorStore
```

What to learn:

- persistent vector database path;
- collection name;
- vector records;
- metadata attached to chunks;
- rebuild vs incremental upsert.

Enterprise extension:

- Qdrant or Milvus for larger deployments;
- metadata filtering;
- collection management;
- incremental upsert/delete.

### 5. Hybrid Search

Files:

- `src/retrieval/bm25.py`
- `src/retrieval/fusion.py`
- `src/retrieval/hybrid.py`
- `src/retrieval/reranker.py`

```text
query
-> Chroma vector search top_k
-> BM25 keyword search top_k
-> Reciprocal Rank Fusion
-> lightweight reranker
-> cited evidence package
```

Configure it in `src/.env`:

```env
VECTOR_TOP_K=20
BM25_TOP_K=20
HYBRID_TOP_K=12
RRF_K=60
RERANKER_ENABLED=true
TOP_K=5
```

### 6. Query Tool And Citation

Files:

- `src/query.py`
- `src/workflow.py`

Current behavior:

- hybrid retrieval returns evidence blocks with `[citation:chunk_id]`;
- the AgentWorkflow system prompt asks the LLM to preserve citations;
- the UI can show source-backed answers.

This is an important enterprise RAG feature because it reduces hallucination and
makes answers auditable.

### 7. Agentic RAG

File: `src/workflow.py`

Current behavior:

```text
AgentWorkflow -> query_index tool -> cited answer
```

This is different from a plain query engine: the LLM can decide when to call the
retrieval tool and can call it multiple times for harder questions.

## How To Run

1. Configure model keys in `src/.env`.

Default setup in this project:

```env
LLM_PROVIDER=deepseek
OPENAI_BASE_URL=https://api.deepseek.com/v1
MODEL=deepseek-chat
# DEEPSEEK_API_KEY=your_key_here

EMBEDDING_PROVIDER=fastembed
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
TOP_K=5

VECTOR_DB=chroma
CHROMA_DB_DIR=src/chroma_db
CHROMA_COLLECTION=enterprise_rag_lab
```

This means:

- DeepSeek is used as the OpenAI-compatible chat model.
- FastEmbed runs BGE embeddings locally for indexing.
- You only need a DeepSeek key for generation; embeddings do not call OpenAI.

If you want to switch back to OpenAI:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your_key_here
MODEL=gpt-4.1
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-large
TOP_K=5
```

2. Add documents to `ui/data/`.

3. Generate the index and write vectors into Chroma:

```bash
uv run generate
```

After generation, you should see:

```text
src/chroma_db/     Chroma vector database files
src/storage/       LlamaIndex index/docstore metadata
```

4. Start the LlamaDeploy API server:

```bash
uv run -m llama_deploy.apiserver
```

5. In another terminal, deploy the workflow:

```bash
uv run llamactl deploy llama_deploy.yml
```

6. Open the UI:

```text
http://localhost:4501/deployments/chat/ui
```

## Suggested Learning Roadmap

### Stage 1: Understand The Generated Template

- Read `src/generate.py`.
- Read `src/query.py`.
- Read `src/workflow.py`.
- Run `uv run generate`.
- Ask questions against the example PDF.

### Stage 2: Explicit Chunking

Read the `TokenTextSplitter(chunk_size=512, chunk_overlap=80)` usage in
`src/ingestion/pipeline.py`.

Experiment with:

- chunk size 256 / 512 / 1024;
- chunk overlap 0 / 80 / 150;
- compare answer quality and retrieved chunks.

### Stage 3: Metadata And Ingestion

Extend ingestion to store metadata:

- `source_path`;
- `file_name`;
- `doc_type`;
- `chunk_id`;
- content hash.

Goal: learn enterprise ingestion instead of one-time PDF upload.

### Stage 4: Vector DB

The project already uses Chroma. Read `src/vector_store.py`, then inspect the
created `src/chroma_db` folder after running `uv run generate`.

Goal: learn vector collections, persistence, upsert, delete, and metadata filter.

### Stage 5: Hybrid Search

The project already includes BM25 retrieval and vector retrieval fusion. Read:

- `src/retrieval/bm25.py`
- `src/retrieval/fusion.py`
- `src/retrieval/hybrid.py`

Then compare retrieval behavior by changing `VECTOR_TOP_K`, `BM25_TOP_K`, and
`RRF_K`.

### Stage 6: Reranker

The project includes a lightweight `LexicalOverlapReranker` in
`src/retrieval/reranker.py`.

It is intentionally simple. Replace it later with:

- BGE reranker;
- Jina reranker API;
- Cohere rerank API;
- any local cross-encoder reranker.

### Stage 7: Evaluation

Run:

```bash
uv run python -m src.eval.run_eval
```

Artifacts:

```text
reports/rag_eval_report.md
reports/rag_eval_report.json
```

Current metrics:

- hit rate;
- MRR;
- average retrieval latency.

Recommended fusion:

- Reciprocal Rank Fusion (RRF);
- then compare with vector-only retrieval.

### Stage 6: Reranker

Pipeline:

```text
query -> hybrid top 30 -> reranker top 5 -> LLM answer with citations
```

Goal: learn high-recall retrieval plus high-precision reranking.

### Stage 7: Evaluation

Build a small `eval/questions.jsonl`:

```json
{"question": "...", "expected_sources": ["..."], "reference_answer": "..."}
```

Track:

- hit rate;
- MRR;
- context recall;
- faithfulness;
- latency;
- token cost.

## Resume Direction

Once extended, describe the project as:

> Built an enterprise-style Agentic RAG system on top of LlamaIndex, supporting
> document ingestion, chunking, embedding-based retrieval, cited answers, and a
> LlamaDeploy chat workflow; extended the baseline with explicit chunking,
> metadata-aware ingestion, vector DB persistence, hybrid search, reranking, and
> evaluation.
