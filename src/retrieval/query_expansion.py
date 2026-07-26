from __future__ import annotations


FINANCE_EXPANSION_TERMS = {
    "capital": "capital expenditures capex capital spending revenue net sales property plant equipment fixed assets total assets net income return on assets consolidated statements of income consolidated balance sheet",
    "capex": "capital expenditures capital spending investing activities property plant equipment",
    "operating margin": "operating income operating profit net sales revenue gross margin impairment litigation restructuring charges",
    "gross margin": "gross profit gross margin net sales revenue cost of sales cost of goods sold",
    "quick ratio": "total current assets inventories inventory total inventories current liabilities total current liabilities cash receivables short term investments consolidated balance sheet",
    "liquidity": "total current assets inventories inventory total current liabilities cash receivables commercial paper debt liquidity consolidated balance sheet",
    "inventory turnover": "cost of sales cost of goods sold inventory inventories turnover",
    "return on assets": "net income total assets average total assets roa",
    "roa": "net income total assets average total assets return on assets",
    "ebitda": "operating income operating profit depreciation amortization capital expenditures capital spending net revenue",
    "cash flow": "operating activities investing activities financing activities net cash provided used capital expenditures",
    "tax rate": "effective tax rate income tax expense benefit income before taxes",
    "segment": "segment net sales revenue organic sales growth acquisition divestiture",
    "organic": "organic sales growth acquisition divestiture foreign currency translation",
    "debt securities": "securities registered section 12(b) notes due trading symbol New York Stock Exchange",
    "repurchase": "share repurchases stock repurchases repurchased shares common stock cost fourth quarter fiscal year total spent program",
    "repurchases": "share repurchases stock repurchases repurchased shares common stock cost fourth quarter fiscal year total spent program",
    "merchandise inventories": "merchandise inventories inventory balance opening new stores store openings cash flow balance sheet",
    "wages": "store payroll benefits wages selling general administrative expenses net sales percentage",
    "sg&a": "selling general administrative expenses SG&A marketing expenses incentive compensation store payroll benefits net sales",
}

GENERIC_FINANCE_TERMS = (
    "annual report form 10-k quarterly report form 10-q consolidated statements "
    "management discussion analysis fiscal year three months six months"
)


def expand_financial_queries(question: str) -> list[str]:
    """Add finance-specific lexical variants for table-heavy questions."""
    normalized = question.lower()
    expansions: list[str] = []

    if "capital-intensive" in normalized or "capital intensive" in normalized:
        expansions.append(f"{question} {FINANCE_EXPANSION_TERMS['capital']}")
    for trigger, terms in FINANCE_EXPANSION_TERMS.items():
        if trigger in normalized:
            expansions.append(f"{question} {terms}")
    if "m&a" in normalized or "acquisition" in normalized or "divestiture" in normalized:
        expansions.append(f"{question} merger acquisition divestiture organic sales growth excluding m&a")
    if "national securities exchange" in normalized:
        expansions.append(f"{question} {FINANCE_EXPANSION_TERMS['debt securities']}")

    expansions.append(f"{question} {GENERIC_FINANCE_TERMS}")

    queries = [question, *expansions]
    return list(dict.fromkeys(queries))
