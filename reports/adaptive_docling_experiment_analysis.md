# Adaptive Docling Evidence Experiment Analysis

Date: 2026-07-07

## Goal

The fixed Docling evidence path improved the full 46-question RAGAS regression, but the
compatibility analysis showed mixed per-question effects. The next hypothesis was that
different question types need different evidence budgets:

- numeric table reasoning should use compact row-level table evidence;
- narrative questions should avoid excessive table rows;
- simple extraction questions may need only one or two high-confidence records;
- domain-specific questions may benefit from finance keyword boosts and filters.

## Experiment

The adaptive experiment added:

- adaptive Docling top-k selection by question type;
- domain-aware fit scoring for repurchases, quick ratio, debt securities, products, and
  EBITDA-style questions;
- optional domain filters for quick ratio, customer concentration, legal, and
  restructuring questions;
- larger candidate retrieval before final evidence selection.

## Full Regression Results

| Run | Faithfulness | Answer relevancy | Answer correctness |
| --- | ---: | ---: | ---: |
| Page-aware baseline | 0.7318 | 0.5373 | 0.4549 |
| Fixed Docling evidence top-5 | 0.7412 | 0.6209 | 0.4989 |
| Adaptive Docling evidence | 0.7475 | 0.5789 | 0.4764 |

## Decision

The adaptive strategy was not adopted as the default. It improved faithfulness slightly,
but it lowered both answer relevancy and answer correctness compared with the fixed
Docling top-5 run.

This means the new heuristics likely made the evidence narrower but not consistently
more useful. In some questions, the filters removed context that the generator needed to
form a complete answer. In other questions, domain boosts made superficially relevant
evidence outrank better supporting context.

## Current Default

The stable default is the fixed Docling evidence top-5 setup:

- `table_top_k=5`
- adaptive Docling top-k disabled;
- domain scoring disabled;
- domain filters disabled;
- broad candidate fusion preserved.

The adaptive logic remains in code as an opt-in experimental path:

- `ADAPTIVE_DOCLING_TOP_K=true`
- `DOCLING_DOMAIN_SCORING_ENABLED=true`
- `DOCLING_DOMAIN_FILTER_ENABLED=true`

## Next Direction

The next improvement should avoid broad heuristic filtering and instead add more
controlled capabilities:

1. a calculator step for questions where retrieved evidence contains the required
   numeric line items;
2. answer templates for ratio, margin, growth, and comparison questions;
3. per-question failure labels so improvements can target categories without harming
   unrelated questions;
4. a smaller validation split for rapid iteration, followed by full 46-question
   regression before accepting any default change.
