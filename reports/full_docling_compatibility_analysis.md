# Full Docling Evidence Compatibility Analysis

## Setup

Full regression command:

```bash
uv run python -m src.eval.run_ragas_eval \
  --questions eval/financebench_questions.jsonl \
  --generation-top-k 6 \
  --neighbor-window 0 \
  --page-top-k 2 \
  --table-top-k 5 \
  --ragas-batch-size 4 \
  --checkpoint-output reports/ragas_eval_full_docling_evidence_checkpoint.json \
  --output reports/ragas_eval_full_docling_evidence.md \
  --json-output reports/ragas_eval_full_docling_evidence.json
```

Full Docling evidence index:

- PDFs parsed: 10
- Parse failures: 0
- Whole tables: 965
- Table rows: 12,074
- Docling text blocks: 2,259
- Indexed evidence records: 15,298

## Overall Result

Compared with `reports/ragas_eval_full_page_v2.json`:

| Metric | Previous full page-aware | Full Docling evidence | Delta |
| --- | ---: | ---: | ---: |
| Faithfulness | 0.7318 | 0.7412 | +0.0094 |
| Answer relevancy | 0.5373 | 0.6209 | +0.0836 |
| Answer correctness | 0.4549 | 0.4989 | +0.0439 |

Correctness movement across 46 questions:

- Improved: 25
- Regressed: 20
- Same: 1

## Largest Correctness Improvements

| Question | Delta | Previous -> New | Prompt |
| --- | ---: | --- | --- |
| Q20 | +0.460 | 0.152 -> 0.611 | Did AMD report customer concentration in FY22? |
| Q4 | +0.422 | 0.193 -> 0.615 | Does 3M have a reasonably healthy liquidity profile based on quick ratio for Q2 FY2023? |
| Q1 | +0.359 | 0.447 -> 0.807 | Is 3M a capital-intensive business based on FY2022 data? |
| Q32 | +0.348 | 0.431 -> 0.779 | Has Boeing reported any materially important ongoing legal battles from FY2022? |
| Q40 | +0.333 | 0.602 -> 0.935 | PepsiCo restructuring costs in FY2022 |
| Q36 | +0.323 | 0.509 -> 0.833 | Boeing production rate changes forecast for FY2023 |
| Q2 | +0.279 | 0.194 -> 0.473 | 3M operating margin change as of FY2022 |
| Q11 | +0.237 | 0.194 -> 0.430 | AMCOR major acquisitions in FY2023/FY2022/FY2021 |

## Largest Correctness Regressions

| Question | Delta | Previous -> New | Prompt |
| --- | ---: | --- | --- |
| Q10 | -0.470 | 0.710 -> 0.240 | AMCOR quick ratio FY2023 vs FY2022 |
| Q21 | -0.318 | 0.802 -> 0.484 | American Express debt securities registered on national securities exchange |
| Q43 | -0.237 | 0.396 -> 0.159 | Ulta SG&A reduction as percent of net sales |
| Q30 | -0.224 | 0.771 -> 0.547 | Best Buy cash flow activity comparison |
| Q15 | -0.190 | 0.780 -> 0.589 | AMD major products and services as of FY2022 |
| Q34 | -0.123 | 0.502 -> 0.379 | Boeing primary customers as of FY2022 |
| Q31 | -0.104 | 0.903 -> 0.798 | Boeing revenue categories over 20% of revenue |
| Q42 | -0.087 | 0.235 -> 0.148 | PepsiCo unadjusted EBITDA margin |

## Compatibility Conclusion

The Docling evidence changes are not overfit to the original 4 Ulta questions: on the
full 46-question regression, all aggregate metrics improved. However, the per-question
movement shows real compatibility risk: table/text evidence can still displace cleaner
chunk/page evidence for some prompts.

The current implementation is acceptable as an experimental improvement, but not yet a
final default. The next optimization should reduce regressions while preserving the
large gains:

1. Lower default Docling evidence budget from `--table-top-k 5` to `--table-top-k 3`
   or make it adaptive by question type.
2. Keep Docling text blocks for questions that need narrative facts, but prefer
   table rows for ratio/line-item calculations.
3. Add a rerank/gate feature based on source agreement and numeric overlap rather than
   blindly appending top-k Docling records.
4. Re-run full regression after each gating change, not only the Ulta subset.
