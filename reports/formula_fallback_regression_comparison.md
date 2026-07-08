# RAGAS Regression Comparison

Baseline: `reports/ragas_eval_full_pdf_element_aware.json`
Candidate: `reports/ragas_eval_full_formula_fallback.json`

Verdict: **FAIL**

| Group | Count | Baseline correctness | Candidate correctness | Correctness delta | Baseline faithfulness | Candidate faithfulness | Faithfulness delta | Baseline relevancy | Candidate relevancy | Relevancy delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 46 | 0.5153 | 0.4865 | -0.0289 | 0.7487 | 0.7726 | 0.0239 | 0.6124 | 0.7158 | 0.1034 |
| target | 3 | 0.4462 | 0.5880 | 0.1418 | 0.4988 | 0.8654 | 0.3666 | 0.2823 | 0.9208 | 0.6385 |
| non_target | 43 | 0.5202 | 0.4794 | -0.0408 | 0.7661 | 0.7661 | -0.0000 | 0.6354 | 0.7014 | 0.0661 |

## Acceptance Rules

- Primary metric: `answer_correctness`
- Target delta must be >= 0.0000: `True`
- Non-target delta must be >= -0.0100: `False`
- Full-set delta must be >= -0.0000: `False`

## Largest Correctness Drops

| Row | Target | Baseline | Candidate | Delta | Question |
| ---: | --- | ---: | ---: | ---: | --- |
| 22 | False | 0.9289 | 0.2333 | -0.6956 | What are the geographies that American Express primarily operates in as of 2022? |
| 46 | False | 0.8124 | 0.1815 | -0.6309 | Did Ulta Beauty's wages expense as a percent of net sales increase or decrease in FY2023? |
| 1 | False | 0.6757 | 0.1648 | -0.5110 | Is 3M a capital-intensive business based on FY2022 data? |
| 40 | False | 0.6534 | 0.1762 | -0.4772 | What is the quantity of restructuring costs directly outlined in Pepsico's income statements for FY2022? If restructuring costs are not explicitly outlined then state 0. |
| 43 | False | 0.5220 | 0.1619 | -0.3601 | What drove the reduction in SG&A expense as a percent of net sales in FY2023? |
| 34 | False | 0.5884 | 0.3221 | -0.2663 | Who are the primary customers of Boeing as of FY2022? |
| 20 | False | 0.8472 | 0.6150 | -0.2321 | Did AMD report customer concentration in FY22? |
| 39 | False | 0.6664 | 0.4694 | -0.1970 | Has Pepsico reported any materially important ongoing legal battles from FY2022 and FY2021? |
| 38 | False | 0.3929 | 0.2060 | -0.1869 | What are the geographies that Pepsico primarily operates in as of FY2022? |
| 16 | False | 0.6840 | 0.5052 | -0.1788 | What drove revenue change as of the FY22 for AMD? |
| 19 | False | 0.5339 | 0.3846 | -0.1493 | From FY21 to FY22, excluding Embedded, in which AMD reporting segment did sales proportionally increase the most? |
| 28 | False | 0.7219 | 0.5950 | -0.1269 | Are Best Buy's gross margins historically consistent (not fluctuating more than roughly 2% each year)? If gross margins are not a relevant metric for a company like this, then please state that and explain why. |

## Largest Correctness Gains

| Row | Target | Baseline | Candidate | Delta | Question |
| ---: | --- | ---: | ---: | ---: | --- |
| 23 | False | 0.1722 | 0.8786 | 0.7064 | Does AMEX have an improving operating margin profile as of 2022? If operating margin is not a useful metric for a company like this, then state that and explain why. |
| 24 | False | 0.4010 | 0.8737 | 0.4726 | What drove gross margin change as of the FY2022 for American Express? If gross margin is not a useful metric for a company like this, then please state that and explain why. |
| 37 | False | 0.4958 | 0.7228 | 0.2270 | How does Boeing's effective tax rate in FY2022 compare to FY2021? |
| 17 | False | 0.3627 | 0.5746 | 0.2119 | What drove operating margin change as of the FY22 for AMD? If operating margin is not a useful metric for a company like this, then please state that and explain why. |
| 14 | True | 0.3097 | 0.5161 | 0.2065 | Does AMD have a reasonably healthy liquidity profile based on its quick ratio for FY22? If the quick ratio is not relevant to measure liquidity, please state that and explain why. |
| 4 | True | 0.3271 | 0.5217 | 0.1946 | Does 3M have a reasonably healthy liquidity profile based on its quick ratio for Q2 of FY2023? If the quick ratio is not relevant to measure liquidity, please state that and explain why. |
| 36 | False | 0.7516 | 0.9423 | 0.1907 | What production rate changes is Boeing forecasting for FY2023? |
| 6 | False | 0.5097 | 0.6532 | 0.1435 | Does 3M maintain a stable trend of dividend distribution? |
| 18 | False | 0.5692 | 0.6931 | 0.1238 | Among operations, investing, and financing activities, which brought in the most (or lost the least) cash flow for AMD in FY22? |
| 41 | False | 0.3335 | 0.4346 | 0.1011 | What is the FY2022 unadjusted EBITDA less capex for PepsiCo? Define unadjusted EBITDA as unadjusted operating income + depreciation and amortization [from cash flow statement]. Answer in USD millions. Respond to the question by assuming the perspective of an investment analyst who can only use the details shown within the statement of cash flows and the income statement. |
| 25 | False | 0.7827 | 0.8731 | 0.0904 | How much has the effective tax rate of American Express changed between FY2021 and FY2022? |
| 21 | False | 0.3225 | 0.4081 | 0.0855 | Which debt securities are registered to trade on a national securities exchange under American Express' name as of 2022? |
