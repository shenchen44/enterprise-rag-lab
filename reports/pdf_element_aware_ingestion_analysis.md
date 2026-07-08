# PDF Element-Aware Ingestion Analysis

Date: 2026-07-08

## Motivation

The previous Docling evidence path already indexed tables, table rows, and text blocks,
but PDF evidence was still missing two important layout-aware signals:

- document section hierarchy;
- repeated PDF furniture/noise handling.

The goal of this iteration was to move the pipeline closer to element-aware PDF
processing instead of treating all extracted content as plain text.

## Changes

Implemented in `src/ingestion/docling_tables.py`:

- added heading-stack parsing for Markdown headings;
- attached `section_path` to table, table row, and Docling text-block metadata;
- prepended `Section:` to retrieval text so embedding and reranking can use section
  context;
- added conservative repeated-short-line filtering for Markdown-derived text blocks;
- added deterministic table profiles containing columns, row count, and sample row
  labels;
- propagated table section metadata to all row-level evidence.

Rebuilt the Docling evidence Chroma collection:

- tables: 965
- table rows: 12,074
- text blocks: 2,259
- indexed records: 15,298

## Validation

Lightweight ingestion assertions passed for:

- section path extraction;
- repeated short-line filtering;
- table profile generation;
- table section metadata.

A retrieval smoke check confirmed newly indexed evidence includes `Section:` text and
`section_path` metadata.

## Full 46-Question RAGAS Regression

| Run | Faithfulness | Answer relevancy | Answer correctness |
| --- | ---: | ---: | ---: |
| Page-aware baseline | 0.7318 | 0.5373 | 0.4549 |
| Fixed Docling evidence top-5 | 0.7412 | 0.6209 | 0.4989 |
| PDF element-aware ingestion | 0.7487 | 0.6124 | 0.5153 |

Compared with fixed Docling evidence top-5:

- faithfulness: +0.0075
- answer relevancy: -0.0086
- answer correctness: +0.0165

Per-question comparison versus fixed Docling evidence top-5:

| Metric | Improved | Worsened | Same |
| --- | ---: | ---: | ---: |
| Faithfulness | 17 | 13 | 16 |
| Answer relevancy | 12 | 10 | 24 |
| Answer correctness | 22 | 24 | 0 |

## Decision

This iteration becomes the new best result for faithfulness and answer correctness.
It does slightly reduce answer relevancy, which suggests section/profile context can make
some retrieved evidence more structured but less directly aligned with the exact question.

The change is worth keeping as the current default evidence index because correctness is
the hardest and most business-relevant metric in this FinanceBench setting, and the
overall correctness gain is larger than the relevancy loss.

## Next Work

1. Add source and period routing to reduce cross-period retrieval, especially 3M 2023Q2
   evidence appearing in FY2022 questions.
2. Add a formula/calculator step for quick ratio, margin, growth, ROA, and tax-rate
   questions.
3. Make table profile weighting configurable if future regressions show it hurts
   relevancy-sensitive questions.
4. Add Docling JSON or PyMuPDF bbox-based header/footer detection for a more precise
   version of the current repeated-line cleaner.
