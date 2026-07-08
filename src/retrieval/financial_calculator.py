from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from src.retrieval.types import RetrievalHit


@dataclass(frozen=True)
class QuickRatioIntent:
    asks_trend: bool = False
    asks_liquidity_health: bool = False
    asks_relevance_caveat: bool = False


QUICK_RATIO_ROW_PATTERNS: tuple[str, ...] = (
    r"cash and cash equivalents",
    r"short-term investments",
    r"marketable securities",
    r"accounts receivable",
    r"receivables from related parties",
    r"^inventories?$",
    r"total inventories",
    r"total current assets",
    r"total current liabilities",
)


def parse_number(value: str) -> float | None:
    cleaned = value.strip()
    if not cleaned or cleaned in {"-", "—", "n/a", "N/A"}:
        return None
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = re.sub(r"[$,%()\s]", "", cleaned.replace(",", ""))
    try:
        number = float(cleaned)
    except ValueError:
        return None
    return -number if negative else number


def extract_row_cells(hit: RetrievalHit) -> tuple[str, dict[str, float], str] | None:
    row_match = re.search(r"^Row:\s*(.+)$", hit.text, flags=re.M)
    if not row_match:
        return None

    row_label = row_match.group(1).strip()
    cells: dict[str, float] = {}
    for header, raw_value in re.findall(r"^-\s*([^:\n]+):\s*(.+)$", hit.text, flags=re.M):
        year_match = re.search(r"(?:19|20)\d{2}", header)
        if not year_match:
            continue
        number = parse_number(raw_value)
        if number is not None:
            cells[year_match.group(0)] = number

    if not cells:
        return None
    return row_label, cells, hit.citation_id


def find_row(
    parsed_rows: list[tuple[str, dict[str, float], str]],
    patterns: tuple[str, ...],
) -> tuple[str, dict[str, float], str] | None:
    for row_label, cells, citation_id in parsed_rows:
        normalized = row_label.lower()
        if any(re.search(pattern, normalized) for pattern in patterns):
            return row_label, cells, citation_id
    return None


def parse_line_values(line: str, years: list[str]) -> dict[str, float]:
    values = [parse_number(value) for value in re.findall(r"\(?\$?\s*[\d,]+(?:\.\d+)?\)?|—", line)]
    values = [value for value in values if value is not None]
    if len(values) < len(years):
        return {}
    return {year: values[-len(years) + idx] for idx, year in enumerate(years)}


def extract_balance_sheet_rows_from_text(hit: RetrievalHit) -> list[tuple[str, dict[str, float], str]]:
    text = hit.text
    if not re.search(r"balance sheets?|current assets|current liabilities", text, re.I):
        return []

    header_match = re.search(r"(?:as of|at)\s+[^,\n]+,\s*((?:19|20)\d{2})\s+((?:19|20)\d{2})", text, re.I)
    years = [header_match.group(1), header_match.group(2)] if header_match else []
    if not years:
        years = re.findall(r"(?:19|20)\d{2}", text)[:2]
    if len(years) < 2:
        return []

    rows: list[tuple[str, dict[str, float], str]] = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    inventory_components: dict[str, float] = {year: 0.0 for year in years}
    in_inventory_block = False
    for line in lines:
        normalized = line.lower()
        if re.search(r"^total current assets\b", normalized):
            rows.append(("Total current assets", parse_line_values(line, years), hit.citation_id))
        elif re.search(r"^total current liabilities\b", normalized):
            rows.append(("Total current liabilities", parse_line_values(line, years), hit.citation_id))

        if re.search(r"^inventories?\b", normalized):
            values = parse_line_values(line, years)
            if values:
                rows.append(("Inventories", values, hit.citation_id))
                in_inventory_block = False
            else:
                in_inventory_block = True
            continue

        if in_inventory_block:
            if re.search(r"prepaid|assets held|total current assets|non-current assets|current liabilities", normalized):
                in_inventory_block = False
                continue
            values = parse_line_values(line, years)
            if values:
                for year, value in values.items():
                    inventory_components[year] += value

    if any(value != 0 for value in inventory_components.values()):
        rows.append(("Inventories", inventory_components, hit.citation_id))
    return [row for row in rows if row[1]]


def canonical_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def source_token_from_path(path: Path) -> str:
    stem = path.stem.lower()
    return re.split(r"(?:19|20)\d{2}|q[1-4]|10k|10q|earnings|annual|quarter", stem)[0].strip("_-")


def candidate_markdown_paths(question: str, root: Path = Path("data/docling/financebench")) -> list[Path]:
    if not root.exists():
        return []

    question_token = canonical_token(question)
    matches: list[Path] = []
    for path in sorted(root.glob("*.md")):
        source_token = canonical_token(source_token_from_path(path))
        if len(source_token) >= 2 and source_token in question_token:
            matches.append(path)

    years = set(question_years(question))
    quarters = set(re.findall(r"\bq[1-4]\b", question.lower()))
    period_matches = [
        path
        for path in matches
        if (not years or any(year in path.stem for year in years))
        and (not quarters or any(quarter in path.stem.lower() for quarter in quarters))
    ]
    return period_matches or matches


def parse_markdown_table_row(line: str, years: list[str]) -> tuple[str, dict[str, float]] | None:
    if not line.lstrip().startswith("|"):
        return None
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    if len(cells) < 2 or set("".join(cells)) <= {"-", ":"}:
        return None

    label = re.sub(r"\s+", " ", cells[0]).strip()
    if not label:
        return None
    values: dict[str, float] = {}
    for year, cell in zip(years, cells[1:]):
        number = parse_number(cell)
        if number is not None:
            values[year] = number
    return (label, values) if values else None


def is_year_header_row(cells: list[str], years: list[str]) -> bool:
    if len(years) < 2:
        return False
    value_cells = [cell for cell in cells[1:] if cell]
    if not value_cells:
        return True
    return all(re.fullmatch(r"(?:19|20)\d{2}", cell.strip()) for cell in value_cells)


def extract_formula_rows_from_markdown(path: Path) -> list[RetrievalHit]:
    rows: list[RetrievalHit] = []
    current_years: list[str] = []
    inside_balance_sheet = False
    saw_balance_sheet_rows = False
    in_inventory_block = False
    inventory_components: dict[str, float] = {}

    def append_inventory_row(line_number: int) -> None:
        nonlocal inventory_components
        if not any(value != 0 for value in inventory_components.values()):
            return
        cell_lines = "\n".join(f"- {year}: {value:g}" for year, value in inventory_components.items())
        rows.append(
            RetrievalHit(
                node_id=f"formula_row:{path.stem}:inventories:{line_number}",
                text=f"Row: Inventories\nCells:\n{cell_lines}",
                metadata={
                    "chunk_id": f"formula_row:{path.stem}:inventories:{line_number}",
                    "source_path": str(path),
                    "retrieval_granularity": "formula_row",
                },
                score=1.5,
                source="formula_fallback",
                debug={"formula_fallback": "markdown_balance_sheet_inventory_block"},
            )
        )
        inventory_components = {}

    for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        normalized_line = line.lower()
        if normalized_line.startswith("##"):
            if re.search(r"\bbalance sheets?\b", normalized_line):
                inside_balance_sheet = True
                saw_balance_sheet_rows = False
                current_years = []
                continue
            if inside_balance_sheet and saw_balance_sheet_rows:
                if in_inventory_block:
                    append_inventory_row(line_number)
                break
            if inside_balance_sheet:
                continue

        if not inside_balance_sheet:
            continue

        if line.lstrip().startswith("|"):
            years = re.findall(r"(?:19|20)\d{2}", line)
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            row_has_numeric_values = any(parse_number(cell) is not None for cell in cells[1:])
            if len(years) >= 2 and (not row_has_numeric_values or is_year_header_row(cells, years)):
                current_years = years
                continue
        if not current_years:
            continue

        if line.lstrip().startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            label = re.sub(r"\s+", " ", cells[0]).strip() if cells else ""
            normalized_label = label.lower()
            inventory_stop = re.search(
                r"total inventories|prepaid|assets held|total current assets|non-current assets|current liabilities",
                normalized_label,
            )
            if in_inventory_block and inventory_stop:
                append_inventory_row(line_number)
                in_inventory_block = False
            if re.search(r"^inventories?\b", normalized_label) and not any(
                parse_number(cell) is not None for cell in cells[1:]
            ):
                inventory_components = {year: 0.0 for year in current_years}
                in_inventory_block = True
                continue

        parsed = parse_markdown_table_row(line, current_years)
        if parsed is None:
            continue
        label, cells = parsed
        normalized = label.lower()
        if in_inventory_block:
            for year, value in cells.items():
                inventory_components[year] = inventory_components.get(year, 0.0) + value
            continue
        if not any(re.search(pattern, normalized) for pattern in QUICK_RATIO_ROW_PATTERNS):
            continue
        cell_lines = "\n".join(f"- {year}: {value:g}" for year, value in cells.items())
        rows.append(
            RetrievalHit(
                node_id=f"formula_row:{path.stem}:{line_number}",
                text=f"Row: {label}\nCells:\n{cell_lines}",
                metadata={
                    "chunk_id": f"formula_row:{path.stem}:{line_number}",
                    "source_path": str(path),
                    "retrieval_granularity": "formula_row",
                },
                score=1.5,
                source="formula_fallback",
                debug={"formula_fallback": "markdown_balance_sheet"},
            )
        )
        saw_balance_sheet_rows = True
    if in_inventory_block:
        append_inventory_row(line_number if "line_number" in locals() else 0)
    return rows


def extract_liability_rows_from_markdown(path: Path) -> list[tuple[str, dict[str, float], str]]:
    rows: list[tuple[str, dict[str, float], str]] = []
    current_years: list[str] = []
    inside_balance_sheet = False
    inside_liabilities = False
    saw_liability_rows = False

    for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        normalized_line = line.lower()
        if normalized_line.startswith("##"):
            if re.search(r"\bbalance sheets?\b", normalized_line):
                inside_balance_sheet = True
                inside_liabilities = False
                saw_liability_rows = False
                current_years = []
                continue
            if inside_balance_sheet and saw_liability_rows:
                break
            if inside_balance_sheet:
                continue

        if not inside_balance_sheet:
            continue

        if line.lstrip().startswith("|"):
            years = re.findall(r"(?:19|20)\d{2}", line)
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            row_has_numeric_values = any(parse_number(cell) is not None for cell in cells[1:])
            if len(years) >= 2 and (not row_has_numeric_values or is_year_header_row(cells, years)):
                current_years = years
                continue
        if not current_years:
            continue

        cells = [cell.strip() for cell in line.strip().strip("|").split("|")] if line.lstrip().startswith("|") else []
        label = re.sub(r"\s+", " ", cells[0]).strip() if cells else ""
        normalized_label = label.lower()
        if normalized_label == "liabilities":
            inside_liabilities = True
            continue
        if not inside_liabilities:
            continue
        if re.search(r"^total liabilities\b|shareholders' equity|stockholders' equity|contingencies", normalized_label):
            break

        parsed = parse_markdown_table_row(line, current_years)
        if parsed is None:
            continue
        row_label, values = parsed
        if re.search(r"\btotal\b|equity|commitments|contingencies", row_label.lower()):
            continue
        rows.append((row_label, values, f"formula_row:{path.stem}:{line_number}"))
        saw_liability_rows = True
    return rows


def build_formula_fallback_hits(question: str) -> list[RetrievalHit]:
    if "quick ratio" not in question.lower() and not should_build_largest_liability_context(question):
        return []
    hits: list[RetrievalHit] = []
    for path in candidate_markdown_paths(question):
        hits.extend(extract_formula_rows_from_markdown(path))
    return hits


def question_years(question: str) -> list[str]:
    years: set[int] = set()
    for fy_value, plain_value in re.findall(
        r"\bfy\s*([0-9]{2}|[0-9]{4})\b|((?:19|20)\d{2})",
        question.lower(),
    ):
        raw = fy_value or plain_value
        year = int(raw)
        years.add(2000 + year if year < 100 else year)
    return [str(year) for year in sorted(years, reverse=True)]


def classify_quick_ratio_intent(question: str) -> QuickRatioIntent:
    normalized = question.lower()
    return QuickRatioIntent(
        asks_trend=bool(re.search(r"\b(improved?|declined?|increase|decrease|change|between)\b", normalized)),
        asks_liquidity_health=bool(re.search(r"\bhealthy|liquidity profile|measure liquidity\b", normalized)),
        asks_relevance_caveat=bool(
            re.search(
                r"not relevant|not something|would ask|please state that|explain why",
                normalized,
            )
        ),
    )


def quick_ratio_guidance(question: str, ratios: list[tuple[str, float]]) -> list[str]:
    intent = classify_quick_ratio_intent(question)
    guidance: list[str] = []

    if intent.asks_trend and len(ratios) >= 2:
        current_year, current_ratio = ratios[0]
        prior_year, prior_ratio = ratios[1]
        direction = "improved" if current_ratio > prior_ratio else "declined" if current_ratio < prior_ratio else "was flat"
        delta_pct = ((current_ratio - prior_ratio) / abs(prior_ratio) * 100) if prior_ratio else 0.0
        guidance.append(
            f"Trend answer cue: quick ratio {direction} from {prior_ratio:.3f} in {prior_year} "
            f"to {current_ratio:.3f} in {current_year} ({delta_pct:+.1f}%)."
        )

    if intent.asks_liquidity_health:
        latest_year, latest_ratio = ratios[0]
        if latest_ratio >= 1:
            health = "reasonably healthy because quick assets exceed current liabilities"
            direct_answer = "Yes"
        else:
            health = "weaker than the usual 1.0x liquidity benchmark because quick assets do not fully cover current liabilities"
            direct_answer = "No"
        guidance.append(
            f"Liquidity answer cue: because the question asks based on quick ratio, start the final answer with "
            f"'{direct_answer}'. {latest_year} quick ratio is {latest_ratio:.3f}, so it is {health}. "
            "Do not override the quick-ratio conclusion with broader management liquidity language."
        )

    if intent.asks_relevance_caveat:
        guidance.append(
            "Relevance cue: the question asks whether quick ratio is relevant; answer the requested quick-ratio result first, "
            "then add any caveat only if the evidence supports an industry-specific reason."
        )

    return guidance


def should_build_largest_liability_context(question: str) -> bool:
    normalized = question.lower()
    return bool(re.search(r"largest liability", normalized) and re.search(r"balance sheet", normalized))


def build_largest_liability_context(question: str, hits: list[RetrievalHit]) -> str:
    if not should_build_largest_liability_context(question):
        return ""

    rows: list[tuple[str, dict[str, float], str]] = [
        row
        for hit in hits
        if (row := extract_row_cells(hit)) is not None
    ]
    for path in candidate_markdown_paths(question):
        rows.extend(extract_liability_rows_from_markdown(path))

    years = question_years(question)
    if not years:
        year_candidates = {year for _, values, _ in rows for year in values}
        years = sorted(year_candidates, reverse=True)
    if not years:
        return ""

    year = years[0]
    candidates: list[tuple[str, float, str]] = []
    for row_label, values, citation_id in rows:
        value = values.get(year)
        if value is None:
            continue
        candidates.append((row_label, value, citation_id))
    if not candidates:
        return ""

    largest_label, largest_value, largest_citation = max(candidates, key=lambda item: item[1])
    sorted_candidates = sorted(candidates, key=lambda item: item[1], reverse=True)
    lines = [
        "Deterministic balance sheet liability comparison aid:",
        f"- {year}: largest liability is {largest_label} at {largest_value:g} based on the liabilities section "
        f"[citation:{largest_citation}].",
        "- Compared liability line items: "
        + "; ".join(f"{label} {value:g}" for label, value, _ in sorted_candidates[:5])
        + ".",
        "Answer guidance:",
        f"- Answer directly with '{largest_label}'. Do not choose Total liabilities because the question asks for the largest liability line item.",
    ]
    return "\n".join(lines)


def build_quick_ratio_context(question: str, hits: list[RetrievalHit]) -> str:
    if "quick ratio" not in question.lower():
        return ""

    parsed_rows = [
        row
        for hit in hits
        if (row := extract_row_cells(hit)) is not None
    ]
    for hit in hits:
        parsed_rows.extend(extract_balance_sheet_rows_from_text(hit))
    current_assets = find_row(parsed_rows, (r"total current assets",))
    inventories = find_row(parsed_rows, (r"inventor",))
    current_liabilities = find_row(parsed_rows, (r"total current liabilities",))
    cash = find_row(parsed_rows, (r"cash and cash equivalents",))
    short_term_investments = find_row(parsed_rows, (r"short-term investments", r"marketable securities"))
    accounts_receivable = find_row(parsed_rows, (r"accounts receivable",))
    related_party_receivables = find_row(parsed_rows, (r"receivables from related parties",))
    if not current_liabilities:
        return ""
    if not ((current_assets and inventories) or (cash and accounts_receivable)):
        return ""

    years = question_years(question)
    if not years:
        years = sorted(
            set(current_assets[1]) & set(inventories[1]) & set(current_liabilities[1]),
            reverse=True,
        )

    lines = ["Deterministic quick ratio calculation aid:"]
    ratios: list[tuple[str, float]] = []
    for year in years:
        liabilities = current_liabilities[1].get(year)
        if liabilities in {None, 0}:
            continue

        explicit_components: list[tuple[str, float, str]] = []
        for label, row in [
            ("cash and cash equivalents", cash),
            ("short-term investments or marketable securities", short_term_investments),
            ("accounts receivable", accounts_receivable),
            ("receivables from related parties", related_party_receivables),
        ]:
            if row and row[1].get(year) is not None:
                explicit_components.append((label, row[1][year], row[2]))

        use_explicit_formula = bool(related_party_receivables and len(explicit_components) >= 3)
        if use_explicit_formula:
            numerator = sum(value for _, value, _ in explicit_components)
            ratio = numerator / liabilities
            component_text = " + ".join(f"{label} {value:g}" for label, value, _ in explicit_components)
            citation_text = ", ".join(f"[citation:{citation_id}]" for _, _, citation_id in explicit_components)
            lines.append(
                "- "
                f"{year}: quick ratio = ({component_text}) / total current liabilities {liabilities:g} "
                f"= {ratio:.3f}. Inputs from {citation_text}, [citation:{current_liabilities[2]}]."
            )
        else:
            if not current_assets or not inventories:
                continue
            assets = current_assets[1].get(year)
            inventory = inventories[1].get(year)
            if assets is None or inventory is None:
                continue
            ratio = (assets - inventory) / liabilities
            lines.append(
                "- "
                f"{year}: quick ratio = (total current assets {assets:g} - inventories {inventory:g}) "
                f"/ total current liabilities {liabilities:g} = {ratio:.3f}. "
                f"Inputs from [citation:{current_assets[2]}], [citation:{inventories[2]}], "
                f"[citation:{current_liabilities[2]}]."
            )
        ratios.append((year, ratio))

    if ratios:
        guidance = quick_ratio_guidance(question, ratios)
        if guidance:
            lines.append("Answer guidance:")
            lines.extend(f"- {cue}" for cue in guidance)

    return "\n".join(lines) if len(lines) > 1 else ""


def build_calculation_context(question: str, hits: list[RetrievalHit]) -> str:
    calculators = [build_quick_ratio_context, build_largest_liability_context]
    sections = [
        section
        for calculator in calculators
        if (section := calculator(question, hits))
    ]
    return "\n\n".join(sections)


def append_calculation_hit(question: str, hits: list[RetrievalHit]) -> list[RetrievalHit]:
    formula_hits = build_formula_fallback_hits(question)
    context = build_calculation_context(question, [*formula_hits, *hits])
    if not context:
        return hits

    calculator_hit = RetrievalHit(
        node_id=f"calculator:{abs(hash(question))}",
        text=context,
        metadata={
            "chunk_id": "deterministic_calculation",
            "source_path": "deterministic_financial_calculator",
            "retrieval_granularity": "calculation",
        },
        score=2.0,
        source="calculator",
        rank=0,
        debug={"calculator": "deterministic_financial_calculator"},
    )
    return [*hits, calculator_hit]
