import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion.docling_tables import (
    build_repeated_line_filter,
    extract_markdown_tables,
    extract_markdown_text_blocks,
    table_profile,
)


def test_section_path_is_attached_to_text_blocks() -> None:
    markdown = """# Annual Report

## Item 7. Management Discussion

Revenue increased to $100 million in fiscal 2023 because sales improved across segments.
Operating income increased to $20 million and cash flow improved by 10%.
"""

    blocks = extract_markdown_text_blocks(markdown, source_path="sample.pdf")

    assert len(blocks) == 1
    assert blocks[0].surrounding_heading == "Item 7. Management Discussion"
    assert blocks[0].section_path == "Annual Report > Item 7. Management Discussion"
    assert "Section: Annual Report > Item 7. Management Discussion" in blocks[0].retrieval_text


def test_repeated_short_lines_are_removed_from_text_blocks() -> None:
    repeated = "\n".join(["Company Annual Report"] * 5)
    markdown = f"""# Report

{repeated}

Revenue increased to $100 million in fiscal 2023 because sales improved across segments.
Operating income increased to $20 million and cash flow improved by 10%.
"""

    repeated_lines = build_repeated_line_filter(markdown, min_repetitions=5)
    blocks = extract_markdown_text_blocks(markdown, source_path="sample.pdf", repeated_lines=repeated_lines)

    assert len(blocks) == 1
    assert "Company Annual Report" not in blocks[0].text
    assert "Revenue increased" in blocks[0].text


def test_table_profile_and_section_metadata() -> None:
    markdown = """# Financial Statements

## Consolidated Statements of Income

| Metric | 2023 | 2022 |
| --- | ---: | ---: |
| Revenue | 100 | 90 |
| Operating income | 20 | 18 |
"""

    tables = extract_markdown_tables(markdown, source_path="sample.pdf")

    assert len(tables) == 1
    assert tables[0].section_path == "Financial Statements > Consolidated Statements of Income"
    assert "columns=Metric, 2023, 2022" in table_profile(tables[0].markdown)
    assert "row_labels=Revenue, Operating income" in tables[0].retrieval_text
    assert tables[0].metadata()["table_row_count"] == 2
