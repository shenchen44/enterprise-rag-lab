# RAGAS Regression Comparison

Baseline: `reports/ragas_eval_full_pdf_element_aware.json`
Candidate: `reports/ragas_eval_full_largest_liability_fallback.json`

Verdict: **FAIL**

| Group | Count | Baseline correctness | Candidate correctness | Correctness delta | Baseline faithfulness | Candidate faithfulness | Faithfulness delta | Baseline relevancy | Candidate relevancy | Relevancy delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 46 | 0.5153 | 0.5212 | 0.0059 | 0.7487 | 0.7898 | 0.0411 | 0.6124 | 0.6927 | 0.0804 |
| target | 4 | 0.3656 | 0.6093 | 0.2437 | 0.5241 | 0.8429 | 0.3187 | 0.4615 | 0.9286 | 0.4671 |
| non_target | 42 | 0.5296 | 0.5129 | -0.0168 | 0.7701 | 0.7848 | 0.0147 | 0.6267 | 0.6703 | 0.0436 |

## Acceptance Rules

- Primary metric: `answer_correctness`
- Target delta must be >= 0.0000: `True`
- Non-target delta must be >= -0.0100: `False`
- Full-set delta must be >= -0.0000: `True`

## Largest Correctness Drops

| Row | Target | Baseline | Candidate | Delta | Question |
| ---: | --- | ---: | ---: | ---: | --- |
| 46 | False | 0.8124 | 0.1821 | -0.6303 | Did Ulta Beauty's wages expense as a percent of net sales increase or decrease in FY2023? |
| 22 | False | 0.9289 | 0.3720 | -0.5569 | What are the geographies that American Express primarily operates in as of 2022? |
| 40 | False | 0.6534 | 0.1766 | -0.4768 | What is the quantity of restructuring costs directly outlined in Pepsico's income statements for FY2022? If restructuring costs are not explicitly outlined then state 0. |
| 43 | False | 0.5220 | 0.1609 | -0.3611 | What drove the reduction in SG&A expense as a percent of net sales in FY2023? |
| 16 | False | 0.6840 | 0.4072 | -0.2768 | What drove revenue change as of the FY22 for AMD? |
| 34 | False | 0.5884 | 0.3832 | -0.2053 | Who are the primary customers of Boeing as of FY2022? |
| 1 | False | 0.6757 | 0.4940 | -0.1817 | Is 3M a capital-intensive business based on FY2022 data? |
| 36 | False | 0.7516 | 0.5852 | -0.1663 | What production rate changes is Boeing forecasting for FY2023? |
| 18 | False | 0.5692 | 0.4105 | -0.1588 | Among operations, investing, and financing activities, which brought in the most (or lost the least) cash flow for AMD in FY22? |
| 2 | False | 0.5871 | 0.4307 | -0.1564 | What drove operating margin change as of FY2022 for 3M? If operating margin is not a useful metric for a company like this, then please state that and explain why. |
| 19 | False | 0.5339 | 0.4012 | -0.1327 | From FY21 to FY22, excluding Embedded, in which AMD reporting segment did sales proportionally increase the most? |
| 39 | False | 0.6664 | 0.5394 | -0.1270 | Has Pepsico reported any materially important ongoing legal battles from FY2022 and FY2021? |

## Largest Correctness Gains

| Row | Target | Baseline | Candidate | Delta | Question |
| ---: | --- | ---: | ---: | ---: | --- |
| 37 | False | 0.4958 | 0.8860 | 0.3902 | How does Boeing's effective tax rate in FY2022 compare to FY2021? |
| 21 | False | 0.3225 | 0.7088 | 0.3863 | Which debt securities are registered to trade on a national securities exchange under American Express' name as of 2022? |
| 26 | True | 0.1236 | 0.4692 | 0.3456 | What was the largest liability in American Express's Balance Sheet in 2022? |
| 17 | False | 0.3627 | 0.6996 | 0.3369 | What drove operating margin change as of the FY22 for AMD? If operating margin is not a useful metric for a company like this, then please state that and explain why. |
| 6 | False | 0.5097 | 0.8228 | 0.3131 | Does 3M maintain a stable trend of dividend distribution? |
| 32 | False | 0.4397 | 0.7480 | 0.3083 | Has Boeing reported any materially important ongoing legal battles from FY2022? |
| 30 | False | 0.4755 | 0.7536 | 0.2781 | Among operations, investing, and financing activities, which brought in the most (or lost the least) cash flow for Best Buy in FY2023? |
| 14 | True | 0.3097 | 0.5625 | 0.2529 | Does AMD have a reasonably healthy liquidity profile based on its quick ratio for FY22? If the quick ratio is not relevant to measure liquidity, please state that and explain why. |
| 4 | True | 0.3271 | 0.5709 | 0.2439 | Does 3M have a reasonably healthy liquidity profile based on its quick ratio for Q2 of FY2023? If the quick ratio is not relevant to measure liquidity, please state that and explain why. |
| 15 | False | 0.6949 | 0.8721 | 0.1773 | What are the major products and services that AMD sells as of FY22? |
| 28 | False | 0.7219 | 0.8675 | 0.1456 | Are Best Buy's gross margins historically consistent (not fluctuating more than roughly 2% each year)? If gross margins are not a relevant metric for a company like this, then please state that and explain why. |
| 7 | False | 0.7459 | 0.8906 | 0.1447 | What is the quantity of restructuring costs directly outlined in AES Corporation's income statements for FY2022? If restructuring costs are not explicitly outlined then state 0. |
