# LlamaIndex Workflow Example

This is a [LlamaIndex](https://www.llamaindex.ai/) project that using [Workflows](https://docs.llamaindex.ai/en/stable/understanding/workflows/) deployed with [LlamaDeploy](https://github.com/run-llama/llama_deploy).

LlamaDeploy is a system for deploying and managing LlamaIndex workflows, while LlamaIndexServer provides a pre-built TypeScript server with an integrated chat UI that can connect directly to LlamaDeploy deployments. This example shows how you can quickly set up a complete chat application by combining these two technologies/

## Enterprise RAG Lab Extensions

This project has been extended from the generated template into an enterprise-style
RAG learning lab:

- DeepSeek as the OpenAI-compatible LLM backend.
- FastEmbed/BGE local embeddings.
- Chroma persistent vector database.
- Explicit ingestion pipeline with metadata, hash dedupe, and configurable chunking.
- BM25 keyword retrieval + Chroma vector retrieval.
- Reciprocal Rank Fusion (RRF) hybrid search.
- Lightweight reranker interface.
- Citation-preserving Agentic RAG workflow.
- Three-layer RAG evaluation: ingestion integrity, retrieval effectiveness,
  and RAGAS generation quality.

Read [STUDY_GUIDE.md](STUDY_GUIDE.md) for the learning roadmap and module map.

## FinanceBench Dataset

This project uses FinanceBench as the first realistic benchmark because it
contains real annual-report PDFs, financial questions, reference answers, and
evidence pages. It is a better resume dataset than toy PDFs because it tests
long-document ingestion, table-heavy retrieval, numerical reasoning evidence,
and citation grounding.

Prepare a lightweight local subset after cloning FinanceBench:

```bash
git clone --depth 1 https://github.com/patronus-ai/financebench.git /private/tmp/financebench
uv run python scripts/prepare_financebench.py \
  --source /private/tmp/financebench \
  --doc-limit 5 \
  --question-limit 20
```

The script copies selected PDFs into `ui/data/financebench/` and writes
`eval/financebench_questions.jsonl`. The PDF directory is git-ignored because
the dataset files are large and can be regenerated.

Rebuild the RAG index and run retrieval evaluation:

```bash
uv run generate
uv run python -m src.eval.run_eval \
  --questions eval/financebench_questions.jsonl \
  --output reports/financebench_eval_report.md \
  --json-output reports/financebench_eval_report.json
```

The retrieval report separates two pre-generation checks:

- **Ingestion integrity**: checks expected-PDF availability, evidence-page
  coverage, page metadata coverage, and chunk-size distribution.
- **Retrieval effectiveness**: checks source hit rate/MRR, evidence-page hit
  rate/MRR, expected-page recall@k, and how much of the reference answer's key
  terms appear in the retrieved contexts.

Use this before RAGAS when changing PDF parsing, chunk size/overlap, embeddings,
hybrid retrieval, reranking, page retrieval, or table retrieval. RAGAS still
answers "did the generated answer look faithful/relevant/correct"; this report
answers "did ingestion preserve the evidence and did retrieval recall it."

The default online retriever also appends page-level evidence after chunk-level
hybrid retrieval:

- `HYBRID_PAGE_TOP_K=10` adds the top page-level hits as supplemental context.
- `PAGE_BM25_ENABLED=true` fuses page-level vector and BM25 results before adding page evidence.
- `HYBRID_TABLE_TOP_K=3` adds table rows for numeric financial questions, filtered to the retrieved filings.
- `FINANCIAL_CALCULATOR_ENABLED=true` appends deterministic evidence for supported financial calculations such as quick ratio and largest-liability questions.
  This improves long-PDF evidence recall without sending the full page index
  through the cross-encoder reranker.
- `SOURCE_SWEEP_ENABLED=false` keeps the heavier source-focused chunk sweep off
  by default. It can be enabled for experiments, but it is slower with BGE-style
  cross-encoder rerankers.

## RAGAS Regression Gate

After any retrieval, ingestion, reranking, prompt, or calculator change, compare the
candidate RAGAS report against the current best baseline before treating it as an
improvement. The regression gate separates target questions from non-target questions,
so a local fix cannot hide broad correctness regressions.

Example: compare a quick-ratio formula fallback run against the current best
PDF-element-aware baseline:

```bash
uv run python scripts/compare_ragas_runs.py \
  --baseline reports/ragas_eval_full_pdf_element_aware.json \
  --candidate reports/ragas_eval_full_formula_fallback.json \
  --target-pattern "quick ratio" \
  --output reports/formula_fallback_regression_comparison.md \
  --json-output reports/formula_fallback_regression_comparison.json \
  --max-non-target-drop 0.01 \
  --max-full-drop 0.0
```

Acceptance policy:

- target questions should improve on `answer_correctness`;
- non-target questions should not drop by more than `0.01`;
- full-set `answer_correctness` should not drop;
- failing candidates stay behind an experimental gate instead of becoming the default
  pipeline.

## Prerequisites

If you haven't installed uv, you can follow the instructions [here](https://docs.astral.sh/uv/getting-started/installation/) to install it.

You can configure [LLM model](https://docs.llamaindex.ai/en/stable/module_guides/models/llms) and [embedding model](https://docs.llamaindex.ai/en/stable/module_guides/models/embeddings) in [src/settings.py](src/settings.py).

Please setup their API keys in the `src/.env` file.

## Installation

Both the SDK and the CLI are part of the LlamaDeploy Python package. To install, just run:

```bash
uv sync
```

If you don't have uv installed, you can follow the instructions [here](https://docs.astral.sh/uv/getting-started/installation/).

## Generate Index

Generate the embeddings of the documents in the `./data` directory:

```shell
uv run generate
```

## Running the Deployment

At this point we have all we need to run this deployment. Ideally, we would have the API server already running
somewhere in the cloud, but to get started let's start an instance locally. Run the following python script
from a shell:

```
$ uv run -m llama_deploy.apiserver
INFO:     Started server process [10842]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:4501 (Press CTRL+C to quit)
```

From another shell, use the CLI, `llamactl`, to create the deployment:

```
$ uv run llamactl deploy llama_deploy.yml
Deployment successful: chat
```

## UI Interface

LlamaDeploy will serve the UI through the apiserver. Point the browser to [http://localhost:4501/deployments/chat/ui](http://localhost:4501/deployments/chat/ui) to interact with your deployment through a user-friendly interface.

## API endpoints

You can find all the endpoints in the [API documentation](http://localhost:4501/docs). To get started, you can try the following endpoints:

Create a new task:

```bash
curl -X POST 'http://localhost:4501/deployments/chat/tasks/create' \
  -H 'Content-Type: application/json' \
  -d '{
    "input": "{\"user_msg\":\"Hello\",\"chat_history\":[]}",
    "service_id": "workflow"
  }'
```

Stream events:

```bash
curl 'http://localhost:4501/deployments/chat/tasks/0b411be6-005d-43f0-9b6b-6a0017f08002/events?session_id=dd36442c-45ca-4eaa-8d75-b4e6dad1a83e&raw_event=true' \
  -H 'Content-Type: application/json'
```

Note that the task_id and session_id are returned when creating a new task.

## Use Case

We have prepared an [example workflow](./src/workflow.py) for the agentic RAG use case, where you can ask questions about the example documents in the [./data](./data) directory.
To update the workflow, you can modify the code in [`src/workflow.py`](src/workflow.py).

## Customize the UI

The UI is served by LLamaIndexServer package, you can configure the UI by modifying the `uiConfig` in the [ui/index.ts](ui/index.ts) file.

The following are the available options:

- `starterQuestions`: Predefined questions for chat interface
- `componentsDir`: Directory for custom event components
- `layoutDir`: Directory for custom layout components
- `llamaDeploy`: The LlamaDeploy configration (deployment name and workflow name that defined in the [llama_deploy.yml](llama_deploy.yml) file)

## LlamaCloud Integration

You can enable LlamaCloud integration by setting the `llamaCloud` option in the [ui/index.ts](ui/index.ts) file.

The following are the available options:

- `outputDir`: The directory for LlamaCloud output

## Learn More

- [LlamaIndex Documentation](https://docs.llamaindex.ai) - learn about LlamaIndex.
- [Workflows Introduction](https://docs.llamaindex.ai/en/stable/understanding/workflows/) - learn about LlamaIndex workflows.
- [LlamaDeploy GitHub Repository](https://github.com/run-llama/llama_deploy)
- [Chat-UI Documentation](https://ts.llamaindex.ai/docs/chat-ui)

You can check out [the LlamaIndex GitHub repository](https://github.com/run-llama/llama_index) - your feedback and contributions are welcome!
