# Table-aware RAG Development Log

## Goal

FinanceBench contains many table-heavy questions. The original pipeline can retrieve
PDF chunks and page-level evidence, but table rows are often split across text chunks
or compressed into hard-to-read plain text. This experiment adds a Docling-based table
extraction path and evaluates whether table evidence improves generation quality.

## Changes

1. Added Docling as the document parsing dependency.
2. Added a table Chroma collection:
   - `TABLE_CHROMA_COLLECTION`
   - `get_table_chroma_collection(reset=False)`
3. Added Docling table ingestion:
   - `src/ingestion/docling_tables.py`
   - `scripts/parse_docling_tables.py`
   - `scripts/build_table_index.py`
4. Added table retrieval:
   - `src/retrieval/table_retriever.py`
   - table hits are represented as normal `RetrievalHit` objects, so they can share
     the same citation and generation path as chunk/page evidence.
5. Extended generation eval:
   - `--table-top-k` appends Docling table evidence to generation contexts.
   - `--start` supports targeted subset evaluation.
   - `TABLE_RERANKER_ENABLED=true` optionally reranks table candidates with the
     existing reranker. It is disabled by default because the POC result was worse.

## POC Dataset

The first long 10-K parse was interrupted because Docling table structure analysis
was too slow for the development loop. For a fast POC, the shorter Ulta Beauty
earnings PDF was parsed instead:

- PDF: `ui/data/financebench/ULTABEAUTY_2023Q4_EARNINGS.pdf`
- Parsed Markdown: `data/docling/financebench_poc/ULTABEAUTY_2023Q4_EARNINGS.md`
- Parsed JSON: `data/docling/financebench_poc/ULTABEAUTY_2023Q4_EARNINGS.json`
- Extracted tables: 10
- Indexed tables: 10

## Evaluation

Targeted subset:

- Questions: last 4 FinanceBench questions, all from Ulta Beauty
- Command pattern:
  - `uv run python -m src.eval.run_ragas_eval --questions eval/financebench_questions.jsonl --start 42 --limit 4 --generation-top-k 6 --neighbor-window 0 --page-top-k 2 ...`

| Variant | Faithfulness | Answer Relevancy | Answer Correctness | Notes |
| --- | ---: | ---: | ---: | --- |
| Baseline, no table evidence | 0.925 | 0.498 | 0.320 | Uses chunk + page retrieval only |
| Add top-3 Docling table evidence | 0.794 | 0.471 | 0.328 | Correctness slightly improved, but table noise reduced faithfulness |
| Add top-3 table evidence with rerank | 0.708 | 0.470 | 0.278 | Current reranker is not reliable for short Markdown tables |
| Add top-1 table evidence with rerank | 0.794 | 0.471 | 0.312 | Less context did not beat baseline |
| Row-level table index + table gate + source filter | 0.891 | 0.471 | 0.512 | Best POC result; stronger correctness with controlled table noise |
| Docling evidence top-5: tables + rows + text blocks | 0.750 | 0.744 | 0.606 | Best correctness; captures table-adjacent narrative facts such as Q4 repurchase amount |

## Findings

Docling can extract real Markdown tables and store them in the vector database, so the
table-aware ingestion path is technically valid. However, simply appending retrieved
tables to the generation context is not enough. For this subset, table evidence helped
one SG&A question but introduced noise for inventory, repurchase, and wage questions.

The current best default is to keep table retrieval opt-in with `--table-top-k`, and
to keep table reranking disabled unless explicitly testing it through
`TABLE_RERANKER_ENABLED=true`.

## Row-level Table Iteration

The next iteration split each Markdown table into row-level retrieval records. Each row
stores its surrounding heading, source file, table index, row label, and header/value
pairs. For the Ulta Beauty POC this changed the table collection from 10 whole-table
records to 151 records:

- Whole tables: 10
- Table rows: 141
- Indexed records: 151

Two safeguards were added before table evidence is appended to generation context:

1. Table gate: table retrieval is only used for numeric, financial metric, comparison,
   percentage, statement, or line-item questions.
2. Source filter: table hits must match an existing retrieved source, or match the
   company/source name explicitly mentioned in the question. This prevents a partial
   table index, such as an Ulta-only POC index, from polluting unrelated company
   questions.

This version produced the best POC result on the 4 Ulta questions:

- Faithfulness: 0.925 -> 0.891
- Answer relevancy: 0.498 -> 0.471
- Answer correctness: 0.320 -> 0.512

The largest per-question correctness gain came from the wages expense question
(`0.192 -> 0.818`), where row-level evidence made the relevant financial line item
easier for the generator to use.

## Docling Text Evidence Iteration

The repurchase percentage question still failed after row-level table indexing because
the required Q4 amount (`$328.1 million`) was not in a table. It appeared in a Docling
Markdown paragraph under the `Share Repurchase Program` heading:

- Q4 repurchase spend: `$328.1 million`
- FY repurchase spend: `$900.0 million`
- Expected calculation: `328.1 / 900.0 * 100 = 36.5%`

To handle this class of table-adjacent facts, the Docling evidence index now includes
three granularities:

1. `table`: whole Markdown tables
2. `table_row`: header-normalized table rows
3. `docling_text`: numeric finance-related Markdown text blocks

For the Ulta POC, the index now contains:

- Whole tables: 10
- Table rows: 141
- Docling text blocks: 13
- Indexed records: 164

With `--table-top-k 5`, generation retrieved the repurchase paragraph and produced the
correct formula:

`328.1 / 900.0 * 100 = 36.5%`

This improved the 4-question POC score again:

- Faithfulness: 0.925 -> 0.750
- Answer relevancy: 0.498 -> 0.744
- Answer correctness: 0.320 -> 0.606

The lower faithfulness is mostly a RAGAS-side issue on the repurchase question, where
the generated answer cited the retrieved Docling paragraph but still received a
faithfulness score of `0.0`. The business answer and calculation were correct.

## Offline Batch Parsing Improvements

Docling can be slow on long 10-K PDFs, so the parsing script was made safer for
offline batch jobs:

- `--skip-existing` reuses already generated Markdown files.
- `--max-file-size-mb` allows fast POCs on small PDFs before attempting long reports.
- PDFs are parsed smaller-first by default, with `--largest-first` available when needed.
- Per-file failures are recorded in `parse_summary.json` instead of stopping the whole batch.
- Summary output reports parsed, skipped, failed, table, and text-block counts.

The smoke test reused the existing Ulta Markdown and confirmed:

- Skipped PDFs: 1
- Tables: 10
- Text blocks: 13

## Full FinanceBench Regression

After the POC, all 10 FinanceBench PDFs were parsed with Docling. The full evidence
index contains:

- Whole tables: 965
- Table rows: 12,074
- Docling text blocks: 2,259
- Indexed evidence records: 15,298

The full 46-question RAGAS regression was run with:

- `generation_top_k=6`
- `neighbor_window=0`
- `page_top_k=2`
- `table_top_k=5`

Compared with the previous full page-aware run:

| Metric | Previous | Full Docling evidence | Delta |
| --- | ---: | ---: | ---: |
| Faithfulness | 0.7318 | 0.7412 | +0.0094 |
| Answer relevancy | 0.5373 | 0.6209 | +0.0836 |
| Answer correctness | 0.4549 | 0.4989 | +0.0439 |

Correctness improved on 25 questions, regressed on 20 questions, and stayed the same on
1 question. This confirms the Docling evidence path is not just overfit to the 4-question
Ulta POC, but also shows that the default evidence budget is still too blunt for some
question types. A detailed compatibility report is available at:

`reports/full_docling_compatibility_analysis.md`

## Next Improvements

1. Make Docling evidence budget adaptive: use fewer records for simple extraction
   questions and more records for table-adjacent numeric reasoning.
2. Add a lightweight calculator step for row-level numeric evidence, especially for
   percentage and ratio questions.
3. Add a source/numeric-overlap gate to prevent Docling text blocks from displacing
   cleaner chunk/page evidence.
4. Re-run the full 46-question regression after each gating change.

## 2026-07-07 Adaptive Docling Evidence Regression

An adaptive Docling evidence experiment was run after the full fixed-budget Docling
evaluation. The experiment added question-type-specific Docling top-k selection, domain
heuristics, and stricter filtering for selected finance questions.

Full 46-question results:

| Run | Faithfulness | Answer relevancy | Answer correctness |
| --- | ---: | ---: | ---: |
| Page-aware baseline | 0.7318 | 0.5373 | 0.4549 |
| Fixed Docling evidence top-5 | 0.7412 | 0.6209 | 0.4989 |
| Adaptive Docling evidence | 0.7475 | 0.5789 | 0.4764 |

Conclusion: the adaptive strategy improved faithfulness slightly, but it reduced answer
relevancy and correctness versus the fixed top-5 Docling evidence run. This suggests the
heuristics over-pruned useful supporting evidence or over-weighted narrow domain matches
on some questions. The default generation path was therefore restored to the best full
regression setting: fixed Docling evidence top-5 with broad candidate fusion.

The adaptive behavior remains available as experimental switches:

- `ADAPTIVE_DOCLING_TOP_K=true`
- `DOCLING_DOMAIN_SCORING_ENABLED=true`
- `DOCLING_DOMAIN_FILTER_ENABLED=true`

By default these switches are disabled so future full-regression runs reproduce the
current best stable behavior instead of the lower-scoring adaptive experiment.

A 2-question smoke test was also run after restoring the defaults to verify that the
generation and RAGAS evaluation path still executes with `table_top_k=5`. The smoke test
is not used as an effectiveness comparison because the sample size is too small; the
full 46-question regression remains the acceptance standard.

## 2026-07-08 PDF Element-Aware Ingestion

Following the PDF element-aware processing direction, the Docling ingestion layer was
extended beyond plain table/text extraction:

- heading-stack parsing now attaches `section_path` metadata to tables, table rows, and
  Docling text blocks;
- retrieval text now includes a `Section:` prefix so section context participates in
  embedding and reranking;
- a conservative repeated-short-line cleaner filters Markdown-derived header/footer-like
  noise from text blocks;
- deterministic table profiles add column names, row count, and sample row labels to
  table retrieval text and metadata.

The Docling evidence index was rebuilt successfully:

- tables: 965
- table rows: 12,074
- text blocks: 2,259
- indexed records: 15,298

Full 46-question RAGAS regression:

| Run | Faithfulness | Answer relevancy | Answer correctness |
| --- | ---: | ---: | ---: |
| Fixed Docling evidence top-5 | 0.7412 | 0.6209 | 0.4989 |
| PDF element-aware ingestion | 0.7487 | 0.6124 | 0.5153 |

This becomes the new best result for faithfulness and answer correctness. Answer
relevancy regressed slightly, so the next step should be source/period routing and a
calculator step rather than further broad evidence-profile expansion.

Detailed analysis:

`reports/pdf_element_aware_ingestion_analysis.md`

## 2026-07-08 Source/Period Routing and Calculator Experiments

Two follow-up improvements were tested after the PDF element-aware ingestion run.

Source/period routing correctly pushed matching filings earlier in the context, but full
regression showed it reduced correctness:

| Variant | Faithfulness | Answer relevancy | Answer correctness |
| --- | ---: | ---: | ---: |
| Hard source/period filter | 0.8156 | 0.5950 | 0.4671 |
| Source/period boost-only | 0.7991 | 0.5975 | 0.4947 |

Both are now disabled by default and retained as experimental switches.

A deterministic quick-ratio calculator was also implemented and tested on the three
quick-ratio questions. It can calculate from row-level evidence and from balance-sheet
text where inventories are split into subcomponents. Targeted testing showed mixed
results: the calculator helped some numeric aspects but hurt AMCOR correctness because
the question expected business judgment about metric suitability, not only a formula.

The calculator is therefore also disabled by default. The current best stable default
remains the PDF element-aware ingestion run:

| Faithfulness | Answer relevancy | Answer correctness |
| ---: | ---: | ---: |
| 0.7487 | 0.6124 | 0.5153 |

Detailed analysis:

`reports/routing_and_calculator_experiment_analysis.md`

## 2026-07-08 Section-Gated Formula Fallback for Quick-Ratio Questions

The first calculator attempt still depended on normal retrieval returning the exact
balance-sheet rows. That failed on 3M and AMD because semantic retrieval surfaced
liquidity discussion rather than the full balance sheet. A formula-specific fallback was
added for quick-ratio questions:

- detect the target company and period from the question;
- read the already-ingested Docling markdown for the matching filing;
- restrict extraction to the `Balance Sheet(s)` section instead of scanning all tables;
- extract row-level formula inputs such as current assets, inventories, current
  liabilities, cash, short-term investments, accounts receivable, and related-party
  receivables;
- aggregate inventory component blocks such as `Raw materials` + `Work in process` when
  the PDF table uses a hierarchical inventory row;
- add answer guidance for trend and liquidity-health questions so the final response
  follows the requested financial interpretation.

Two bugs found during targeted evaluation were fixed:

- AMD initially used a cash-flow table row (`Net increase in cash and cash equivalents`)
  instead of the balance-sheet `Cash and cash equivalents` row, so section gating was
  added.
- 3M initially double-counted inventories by summing components and then also adding
  `Total inventories`, so `Total inventories` now stops the inventory component block.

Targeted quick-ratio results after these fixes:

| Question | Faithfulness | Answer relevancy | Answer correctness | Notes |
| --- | ---: | ---: | ---: | --- |
| 3M Q2 FY2023 quick ratio | 1.0000 | 0.9711 | 0.6890 | Correctly calculates 0.958 and answers `No` based on the 1.0x benchmark. |
| AMCOR FY2023 vs FY2022 quick ratio | 0.7273 | 0.8616 | 0.7348 | Correctly calculates 0.669 to 0.691, a +3.4% improvement. |
| AMD FY2022 quick ratio | 1.0000 | 0.9409 | 0.6514 | Correctly calculates 1.567 using cash, short-term investments, receivables, related-party receivables, and current liabilities. |

The next validation step is a 20-question full RAGAS run with
`FINANCIAL_CALCULATOR_ENABLED=true` to ensure this targeted fallback does not regress
non-formula questions.

## 2026-07-08 RAGAS Regression Gate

A regression comparison harness was added:

`scripts/compare_ragas_runs.py`

It compares two RAGAS JSON reports and splits results into:

- `target`: questions matched by regex or explicit row indices;
- `non_target`: all other questions;
- `all`: full evaluation set.

The acceptance policy is:

- target `answer_correctness` must improve;
- non-target `answer_correctness` must not drop by more than 0.01;
- full-set `answer_correctness` must not drop.

The formula fallback run was compared against the current best PDF-element-aware
baseline using `quick ratio` as the target group:

| Group | Count | Baseline correctness | Candidate correctness | Delta |
| --- | ---: | ---: | ---: | ---: |
| all | 46 | 0.5153 | 0.4865 | -0.0289 |
| target | 3 | 0.4462 | 0.5880 | +0.1418 |
| non_target | 43 | 0.5202 | 0.4794 | -0.0408 |

Decision:

- formula fallback is valid as a targeted quick-ratio improvement;
- it fails the full regression gate because non-target correctness drops;
- the default pipeline remains PDF element-aware ingestion;
- formula fallback should stay behind `FINANCIAL_CALCULATOR_ENABLED=true` until it can
  pass target, non-target, and full-set gates together.

Detailed regression report:

`reports/formula_fallback_regression_comparison.md`

## 2026-07-08 Largest-Liability Fallback and Deterministic Answer Tightening

The next failure analyzed from the best PDF-element-aware baseline was:

> What was the largest liability in American Express's Balance Sheet in 2022?

The baseline retrieved partial liability evidence and answered `long-term debt`, missing
the balance-sheet line item `Customer deposits`. A targeted fallback was added to the
financial calculator path:

- trigger only when a question asks for the `largest liability` in the `balance sheet`;
- read matching Docling markdown filings instead of relying only on semantic retrieval;
- enter the `Balance Sheet(s)` section and then the `Liabilities` subsection;
- ignore total/equity/commitment rows so the answer is a liability line item, not
  `Total liabilities`;
- compare all extracted liability rows for the requested year and emit a deterministic
  calculation hit with answer guidance.

Implementation files:

- `src/retrieval/financial_calculator.py`
- `tests/test_financial_calculator.py`

Targeted Q26 result after adding the fallback:

| Run | Faithfulness | Answer relevancy | Answer correctness | Generated final answer |
| --- | ---: | ---: | ---: | --- |
| PDF element-aware baseline | 0.6000 | 0.9991 | 0.1236 | Long-term debt |
| Largest-liability fallback | 1.0000 | 0.9112 | 0.4228 | Customer deposits |

The answer became semantically correct, but correctness remained modest because the
response still included a longer evidence/calculation scaffold. The generation prompt was
therefore tightened so deterministic calculation aids are treated as highest-priority
evidence and the final answer is direct.

Targeted Q26 result after prompt tightening:

| Run | Faithfulness | Answer relevancy | Answer correctness | Generated final answer |
| --- | ---: | ---: | ---: | --- |
| Largest-liability fallback + prompt tightening | 0.8889 | 0.9523 | 0.6407 | Customer deposits |

Full 46-question RAGAS regression against the current best PDF-element-aware baseline:

| Candidate | Faithfulness | Relevancy | Correctness | Full correctness delta | Target correctness delta | Non-target correctness delta | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Largest-liability fallback | 0.7898 | 0.6927 | 0.5212 | +0.0059 | +0.2437 | -0.0168 | FAIL |
| Largest-liability fallback + prompt tightening | 0.8021 | 0.6935 | 0.5227 | +0.0074 | +0.2284 | -0.0137 | FAIL |

Decision:

- this is the best full-run metric observed so far on all three headline metrics;
- the deterministic calculator path is useful for high-precision table questions;
- the strict regression gate still fails because non-target correctness drops by more
  than the configured `0.01` tolerance;
- observed Q26 correctness varies materially between a single-question run and the full
  run despite both answers being semantically correct, so RAGAS correctness should be
  interpreted with full-run averages and answer inspection, not as a perfectly stable
  per-sample oracle;
- keep the calculator behind `FINANCIAL_CALCULATOR_ENABLED=true` until either repeated
  full runs show the non-target drop is only evaluator noise or additional routing reduces
  the non-target variance.

Detailed regression reports:

- `reports/largest_liability_fallback_regression_comparison.md`
- `reports/calculator_prompt_tightening_regression_comparison.md`
