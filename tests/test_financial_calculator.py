import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.retrieval.financial_calculator import (
    append_calculation_hit,
    build_calculation_context,
    classify_quick_ratio_intent,
    extract_effective_tax_rate_rows_from_markdown,
    extract_formula_rows_from_markdown,
    extract_liability_rows_from_markdown,
    parse_number,
)
from src.retrieval.types import RetrievalHit


def row_hit(node_id: str, row_label: str, cells: dict[str, str]) -> RetrievalHit:
    cell_lines = "\n".join(f"- {header}: {value}" for header, value in cells.items())
    return RetrievalHit(
        node_id=node_id,
        text=f"Row: {row_label}\nCells:\n{cell_lines}",
        metadata={"chunk_id": node_id},
        score=1.0,
        source="test",
    )


def test_parse_number_handles_financial_formats() -> None:
    assert parse_number("$1,234") == 1234
    assert parse_number("(123)") == -123
    assert parse_number("(0.6)%") == -0.6
    assert parse_number("($1,234.5)") == -1234.5
    assert parse_number("12.5%") == 12.5
    assert parse_number("—") is None


def test_build_quick_ratio_context_from_table_rows() -> None:
    hits = [
        row_hit("assets", "Total current assets", {"2023": "1,000", "2022": "900"}),
        row_hit("inventory", "Inventories", {"2023": "250", "2022": "300"}),
        row_hit("liabilities", "Total current liabilities", {"2023": "500", "2022": "400"}),
    ]

    context = build_calculation_context(
        "Has the quick ratio improved or declined between FY2023 and FY2022?",
        hits,
    )

    assert "2023: quick ratio = (total current assets 1000 - inventories 250)" in context
    assert "= 1.500" in context
    assert "2022: quick ratio" in context
    assert "= 1.500" in context
    assert "[citation:assets]" in context
    assert "Trend answer cue" in context


def test_classify_quick_ratio_intent_detects_relevance_and_health() -> None:
    intent = classify_quick_ratio_intent(
        "Does AMD have a reasonably healthy liquidity profile based on its quick ratio for FY22? "
        "If the quick ratio is not relevant to measure liquidity, please state that and explain why."
    )

    assert intent.asks_liquidity_health is True
    assert intent.asks_relevance_caveat is True
    assert intent.asks_trend is False


def test_append_calculation_hit_only_when_formula_inputs_exist() -> None:
    hits = [
        row_hit("assets", "Total current assets", {"2023": "1,000"}),
        row_hit("inventory", "Inventories", {"2023": "250"}),
        row_hit("liabilities", "Total current liabilities", {"2023": "500"}),
    ]

    augmented = append_calculation_hit("What is the quick ratio in FY2023?", hits)

    assert len(augmented) == 4
    assert augmented[-1].source == "calculator"
    assert augmented[-1].metadata["chunk_id"] == "deterministic_calculation"


def test_quick_ratio_context_from_balance_sheet_text() -> None:
    hit = RetrievalHit(
        node_id="balance-sheet",
        text="""Consolidated Balance Sheets
As of June 30, 2023 2022
Current assets:
Inventories, net
Raw materials and supplies 992 1,114
Work in process and finished goods 1,221 1,325
Total current assets 5,308 5,853
Current liabilities:
Total current liabilities 4,476 5,103
""",
        metadata={"chunk_id": "balance-sheet"},
        score=1.0,
        source="test",
    )

    context = build_calculation_context(
        "Has AMCOR's quick ratio improved or declined between FY2023 and FY2022?",
        [hit],
    )

    assert "2023: quick ratio" in context
    assert "inventories 2213" in context
    assert "= 0.691" in context
    assert "2022: quick ratio" in context
    assert "inventories 2439" in context
    assert "= 0.669" in context
    assert "quick ratio improved from 0.669 in 2022 to 0.691 in 2023" in context


def test_extract_formula_rows_from_markdown_table(tmp_path) -> None:
    markdown = tmp_path / "AMD_2022_10K.md"
    markdown.write_text(
        """## Consolidated Balance Sheets
|                                 | December 31, 2022 | December 25, 2021 |
|---------------------------------|-------------------|-------------------|
| Cash and cash equivalents       | $ 4,835           | $ 2,535           |
| Short-term investments          | 1,020             | 1,073             |
| Accounts receivable, net        | 4,126             | 2,706             |
| Inventories                     | 3,771             | 1,955             |
| Receivables from related parties| 2                 | 2                 |
| Total current liabilities       | 6,369             | 4,240             |
""",
        encoding="utf-8",
    )

    rows = extract_formula_rows_from_markdown(markdown)

    assert any("Row: Cash and cash equivalents" in row.text for row in rows)
    assert any("Row: Total current liabilities" in row.text for row in rows)
    assert any("- 2022: 4835" in row.text for row in rows)


def test_extract_formula_rows_aggregates_inventory_block_without_double_counting(tmp_path) -> None:
    markdown = tmp_path / "3M_2023Q2_10Q.md"
    markdown.write_text(
        """## Consolidated Balance Sheet
|                          | June 30, 2023 | December 31, 2022 |
|--------------------------|---------------|-------------------|
| Current assets           |               |                   |
| Inventories              |               |                   |
| Finished goods           | 2,526         | 2,497             |
| Work in process          | 1,527         | 1,606             |
| Raw materials and supplies | 1,227       | 1,269             |
| Total inventories        | 5,280         | 5,372             |
| Total current assets     | 15,754        | 14,688            |
| Total current liabilities| 10,936        | 9,523             |
""",
        encoding="utf-8",
    )

    rows = extract_formula_rows_from_markdown(markdown)
    inventory_rows = [row for row in rows if "Row: Inventories" in row.text]

    assert inventory_rows
    assert "- 2023: 5280" in inventory_rows[0].text
    assert "- 2023: 10560" not in inventory_rows[0].text


def test_extract_liability_rows_from_balance_sheet(tmp_path) -> None:
    markdown = tmp_path / "AMERICANEXPRESS_2022_10K.md"
    markdown.write_text(
        """## Consolidated Balance Sheets
|                                      | December 31, 2022 | December 31, 2021 |
|--------------------------------------|-------------------|-------------------|
| Total assets                         | $ 228,354         | $ 188,548         |
| Liabilities and Shareholders' Equity |                   |                   |
| Liabilities                          |                   |                   |
| Customer deposits                    | $ 110,239         | $ 84,382          |
| Accounts payable                     | 12,133            | 10,574            |
| Long-term debt                       | 42,573            | 38,675            |
| Other liabilities                    | 37,350            | 30,497            |
| Total liabilities                    | $ 203,643         | $ 166,371         |
| Shareholders' Equity                 |                   |                   |
""",
        encoding="utf-8",
    )

    rows = extract_liability_rows_from_markdown(markdown)

    assert ("Customer deposits", {"2022": 110239.0, "2021": 84382.0}, "formula_row:AMERICANEXPRESS_2022_10K:7") in rows
    assert not any(row_label == "Total liabilities" for row_label, _, _ in rows)


def test_largest_liability_context_selects_largest_line_item(tmp_path, monkeypatch) -> None:
    financebench = tmp_path / "data" / "docling" / "financebench"
    financebench.mkdir(parents=True)
    markdown = financebench / "AMERICANEXPRESS_2022_10K.md"
    markdown.write_text(
        """## Consolidated Balance Sheets
|                                      | December 31, 2022 | December 31, 2021 |
|--------------------------------------|-------------------|-------------------|
| Liabilities and Shareholders' Equity |                   |                   |
| Liabilities                          |                   |                   |
| Customer deposits                    | $ 110,239         | $ 84,382          |
| Accounts payable                     | 12,133            | 10,574            |
| Long-term debt                       | 42,573            | 38,675            |
| Other liabilities                    | 37,350            | 30,497            |
| Total liabilities                    | $ 203,643         | $ 166,371         |
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    context = build_calculation_context(
        "What was the largest liability in American Express's Balance Sheet in 2022?",
        [],
    )

    assert "largest liability is Customer deposits at 110239" in context
    assert "Answer directly with 'Customer deposits'" in context


def test_build_effective_tax_rate_context_uses_consistent_signs() -> None:
    hits = [
        row_hit("pre-tax", "Loss before income taxes", {"2022": "($5,022)", "2021": "($5,033)"}),
        row_hit("tax", "Income tax (expense)/benefit", {"2022": "(31)", "2021": "743"}),
    ]

    context = build_calculation_context(
        "How does Boeing's effective tax rate in FY2022 compare to FY2021?",
        hits,
    )

    assert "2022: effective tax rate = 31 / abs(-5022) x 100 = 0.617%" in context
    assert "2021: effective tax rate = -743 / abs(-5033) x 100 = -14.763%" in context
    assert "[citation:tax]" in context
    assert "[citation:pre-tax]" in context


def test_extract_effective_tax_rate_rows_from_markdown(tmp_path) -> None:
    markdown = tmp_path / "BOEING_2022_10K.md"
    markdown.write_text(
        """## Consolidated Statements of Operations
| Years ended December 31 | 2022 | 2021 |
|---|---:|---:|
| Loss before income taxes | ($5,022) | ($5,033) |
| Income tax (expense)/benefit | (31) | 743 |
""",
        encoding="utf-8",
    )

    rows = extract_effective_tax_rate_rows_from_markdown(markdown)

    assert any("Row: Loss before income taxes" in row.text for row in rows)
    assert any("Row: Income tax (expense)/benefit" in row.text for row in rows)
    assert any("- 2022: -5022" in row.text for row in rows)
