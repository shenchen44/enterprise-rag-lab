# Source/Period Routing and Calculator Experiment Analysis

Date: 2026-07-08

## Baseline

The current best stable run is still PDF element-aware ingestion:

| Run | Faithfulness | Answer relevancy | Answer correctness |
| --- | ---: | ---: | ---: |
| PDF element-aware ingestion | 0.7487 | 0.6124 | 0.5153 |

## Source/Period Routing

Two source/period routing variants were tested:

| Variant | Faithfulness | Answer relevancy | Answer correctness |
| --- | ---: | ---: | ---: |
| Hard filter | 0.8156 | 0.5950 | 0.4671 |
| Boost-only | 0.7991 | 0.5975 | 0.4947 |

The routing logic correctly pushes matching sources, for example ranking `3M_2022_10K`
above `3M_2023Q2_10Q` for FY2022 questions. However, full regression showed that both
variants reduce answer correctness versus the current best run.

Decision:

- keep `src/retrieval/source_period.py` as an experimental module;
- keep `SOURCE_PERIOD_ROUTING_ENABLED=false` by default;
- keep `SOURCE_PERIOD_FILTER_ENABLED=false` by default.

## Quick Ratio Calculator

A deterministic quick-ratio calculator was implemented as an experimental generation aid.
It can extract:

- total current assets;
- inventories, including inventory subcomponents in balance-sheet text;
- total current liabilities.

It then appends a synthetic calculation evidence item when enabled.

Targeted quick-ratio checks versus the current best run:

| Question index | Faithfulness delta | Relevancy delta | Correctness delta | Calculator evidence |
| ---: | ---: | ---: | ---: | --- |
| 3 | -0.3317 | +0.8707 | +0.0951 | no |
| 9 | +0.6667 | +0.0052 | -0.1982 | yes |
| 13 | -0.0273 | +0.0000 | +0.0081 | no |

The AMCOR case shows the risk clearly: the formula evidence was correct, but correctness
dropped because the question also asks whether quick ratio is an appropriate analyst
metric for the company. The generated answer became more formula-centric than the
reference answer expected.

Decision:

- keep `src/retrieval/financial_calculator.py` as an experimental module;
- keep `FINANCIAL_CALCULATOR_ENABLED=false` by default;
- do not run a full regression with calculator enabled until the calculator is paired
  with a question-intent gate and answer template.

## Next Direction

The next improvement should be more targeted than broad routing:

1. add question-intent detection before calculator use;
2. only inject calculator evidence for questions that explicitly ask for a numeric value
   or comparison, not for questions centered on metric suitability;
3. add answer templates that preserve both calculation and business interpretation;
4. evaluate on targeted formula questions before running full regression.
