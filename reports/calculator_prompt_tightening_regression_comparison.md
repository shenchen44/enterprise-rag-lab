# RAGAS Regression Comparison

Baseline: `reports/ragas_eval_full_pdf_element_aware.json`
Candidate: `reports/ragas_eval_full_calculator_prompt_tightening.json`

Verdict: **FAIL**

| Group | Count | Baseline correctness | Candidate correctness | Correctness delta | Baseline faithfulness | Candidate faithfulness | Faithfulness delta | Baseline relevancy | Candidate relevancy | Relevancy delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 46 | 0.5153 | 0.5227 | 0.0074 | 0.7487 | 0.8021 | 0.0534 | 0.6124 | 0.6935 | 0.0811 |
| target | 4 | 0.3656 | 0.5940 | 0.2284 | 0.5241 | 0.9464 | 0.4223 | 0.4615 | 0.9372 | 0.4757 |
| non_target | 42 | 0.5296 | 0.5159 | -0.0137 | 0.7701 | 0.7883 | 0.0182 | 0.6267 | 0.6703 | 0.0435 |

## Acceptance Rules

- Primary metric: `answer_correctness`
- Target delta must be >= 0.0000: `True`
- Non-target delta must be >= -0.0100: `False`
- Full-set delta must be >= -0.0000: `True`

## Largest Correctness Drops

| Row | Target | Baseline | Candidate | Delta | Question |
| ---: | --- | ---: | ---: | ---: | --- |
| 22 | False | 0.9289 | 0.2286 | -0.7003 | What are the geographies that American Express primarily operates in as of 2022? |
| 46 | False | 0.8124 | 0.1912 | -0.6212 | Did Ulta Beauty's wages expense as a percent of net sales increase or decrease in FY2023? |
| 40 | False | 0.6534 | 0.1741 | -0.4793 | What is the quantity of restructuring costs directly outlined in Pepsico's income statements for FY2022? If restructuring costs are not explicitly outlined then state 0. |
| 43 | False | 0.5220 | 0.1746 | -0.3474 | What drove the reduction in SG&A expense as a percent of net sales in FY2023? |
| 12 | False | 0.9577 | 0.6529 | -0.3048 | What industry does AMCOR primarily operate in? |
| 39 | False | 0.6664 | 0.4234 | -0.2430 | Has Pepsico reported any materially important ongoing legal battles from FY2022 and FY2021? |
| 19 | False | 0.5339 | 0.3237 | -0.2102 | From FY21 to FY22, excluding Embedded, in which AMD reporting segment did sales proportionally increase the most? |
| 34 | False | 0.5884 | 0.3826 | -0.2058 | Who are the primary customers of Boeing as of FY2022? |
| 36 | False | 0.7516 | 0.6326 | -0.1190 | What production rate changes is Boeing forecasting for FY2023? |
| 16 | False | 0.6840 | 0.5692 | -0.1148 | What drove revenue change as of the FY22 for AMD? |
| 10 | True | 0.7019 | 0.6079 | -0.0940 | Has AMCOR's quick ratio improved or declined between FY2023 and FY2022? If the quick ratio is not something that a financial analyst would ask about a company like this, then state that and explain why. |
| 7 | False | 0.7459 | 0.7068 | -0.0391 | What is the quantity of restructuring costs directly outlined in AES Corporation's income statements for FY2022? If restructuring costs are not explicitly outlined then state 0. |

## Largest Correctness Gains

| Row | Target | Baseline | Candidate | Delta | Question |
| ---: | --- | ---: | ---: | ---: | --- |
| 14 | True | 0.3097 | 0.8779 | 0.5682 | Does AMD have a reasonably healthy liquidity profile based on its quick ratio for FY22? If the quick ratio is not relevant to measure liquidity, please state that and explain why. |
| 35 | False | 0.3964 | 0.7998 | 0.4034 | Is Boeing's business subject to cyclicality? |
| 15 | False | 0.6949 | 0.9297 | 0.2348 | What are the major products and services that AMD sells as of FY22? |
| 29 | False | 0.5945 | 0.8291 | 0.2345 | What are major acquisitions that Best Buy has done in FY2023, FY2022 and FY2021? |
| 26 | True | 0.1236 | 0.3542 | 0.2306 | What was the largest liability in American Express's Balance Sheet in 2022? |
| 17 | False | 0.3627 | 0.5730 | 0.2103 | What drove operating margin change as of the FY22 for AMD? If operating margin is not a useful metric for a company like this, then please state that and explain why. |
| 4 | True | 0.3271 | 0.5358 | 0.2087 | Does 3M have a reasonably healthy liquidity profile based on its quick ratio for Q2 of FY2023? If the quick ratio is not relevant to measure liquidity, please state that and explain why. |
| 30 | False | 0.4755 | 0.6812 | 0.2057 | Among operations, investing, and financing activities, which brought in the most (or lost the least) cash flow for Best Buy in FY2023? |
| 6 | False | 0.5097 | 0.7102 | 0.2005 | Does 3M maintain a stable trend of dividend distribution? |
| 13 | False | 0.3473 | 0.5395 | 0.1922 | Does AMCOR have an improving gross margin profile as of FY2023? If gross margin is not a useful metric for a company like this, then state that and explain why. |
| 25 | False | 0.7827 | 0.9704 | 0.1877 | How much has the effective tax rate of American Express changed between FY2021 and FY2022? |
| 38 | False | 0.3929 | 0.5626 | 0.1698 | What are the geographies that Pepsico primarily operates in as of FY2022? |
