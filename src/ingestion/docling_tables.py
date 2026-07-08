from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from llama_index.core import Settings

from src.vector_store import get_table_chroma_collection

MarkdownTableRecord = "ExtractedTable | ExtractedTableRow"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("<br>", " ").strip())


def normalize_repeated_line(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def heading_level(line: str) -> int:
    match = re.match(r"^(#{1,6})\s+", line.lstrip())
    return len(match.group(1)) if match else 0


def heading_text(line: str) -> str:
    return line.lstrip("#").strip()


def update_heading_stack(stack: list[tuple[int, str]], line: str) -> list[tuple[int, str]]:
    level = heading_level(line)
    if level <= 0:
        return stack
    text = heading_text(line)
    stack = [(existing_level, title) for existing_level, title in stack if existing_level < level]
    stack.append((level, text))
    return stack


def section_path_from_stack(stack: list[tuple[int, str]]) -> str:
    return " > ".join(title for _level, title in stack if title)


def build_repeated_line_filter(markdown: str, *, min_repetitions: int = 5) -> set[str]:
    """Approximate header/footer removal from Markdown by repeated short lines.

    Docling Markdown does not expose page coordinates, so this is a conservative
    fallback for repeated page furniture such as company names, form labels, and
    page numbers. It only targets short non-table lines that repeat many times.
    """
    counter: Counter[str] = Counter()
    for line in markdown.splitlines():
        stripped = clean_cell(line)
        if not stripped or is_markdown_table_line(stripped) or is_markdown_table_separator(stripped):
            continue
        if stripped.startswith("#"):
            stripped = heading_text(stripped)
        if len(stripped) > 120:
            continue
        normalized = normalize_repeated_line(stripped)
        if len(normalized) < 3 or normalized.isdigit():
            continue
        counter[normalized] += 1
    return {line for line, count in counter.items() if count >= min_repetitions}


def is_repeated_noise_line(line: str, repeated_lines: set[str]) -> bool:
    if not repeated_lines:
        return False
    stripped = clean_cell(line)
    if stripped.startswith("#"):
        stripped = heading_text(stripped)
    if len(stripped) > 120:
        return False
    return normalize_repeated_line(stripped) in repeated_lines


@dataclass(slots=True)
class ExtractedTable:
    table_id: str
    source_path: str
    file_name: str
    table_index: int
    markdown: str
    surrounding_heading: str
    section_path: str = ""

    @property
    def retrieval_text(self) -> str:
        heading = f"Heading: {self.surrounding_heading}\n" if self.surrounding_heading else ""
        section = f"Section: {self.section_path}\n" if self.section_path else ""
        profile = f"Table profile: {table_profile(self.markdown)}\n"
        return f"{section}{heading}Source: {self.file_name}\n{profile}Table:\n{self.markdown}"

    def metadata(self) -> dict:
        headers, row_labels = table_headers_and_row_labels(self.markdown)
        return {
            "table_id": self.table_id,
            "source_path": self.source_path,
            "file_name": self.file_name,
            "table_index": self.table_index,
            "surrounding_heading": self.surrounding_heading,
            "section_path": self.section_path,
            "table_headers": " | ".join(headers[:20]),
            "table_row_label_sample": " | ".join(row_labels[:20]),
            "table_row_count": len(row_labels),
            "retrieval_granularity": "table",
            "content_hash": sha256_text(self.markdown),
        }


@dataclass(slots=True)
class ExtractedTableRow:
    row_id: str
    table_id: str
    source_path: str
    file_name: str
    table_index: int
    row_index: int
    row_label: str
    cells: dict[str, str]
    surrounding_heading: str
    section_path: str = ""

    @property
    def retrieval_text(self) -> str:
        heading = f"Heading: {self.surrounding_heading}\n" if self.surrounding_heading else ""
        section = f"Section: {self.section_path}\n" if self.section_path else ""
        row_label = f"Row: {self.row_label}\n" if self.row_label else ""
        cell_lines = "\n".join(f"- {header}: {value}" for header, value in self.cells.items() if value)
        return (
            f"{section}"
            f"{heading}"
            f"Source: {self.file_name}\n"
            f"Table index: {self.table_index}\n"
            f"{row_label}"
            f"Cells:\n{cell_lines}"
        )

    def metadata(self) -> dict:
        return {
            "row_id": self.row_id,
            "table_id": self.table_id,
            "source_path": self.source_path,
            "file_name": self.file_name,
            "table_index": self.table_index,
            "row_index": self.row_index,
            "row_label": self.row_label,
            "surrounding_heading": self.surrounding_heading,
            "section_path": self.section_path,
            "retrieval_granularity": "table_row",
            "content_hash": sha256_text(json.dumps(self.cells, sort_keys=True)),
        }


@dataclass(slots=True)
class ExtractedTextBlock:
    block_id: str
    source_path: str
    file_name: str
    block_index: int
    text: str
    surrounding_heading: str
    section_path: str = ""

    @property
    def retrieval_text(self) -> str:
        heading = f"Heading: {self.surrounding_heading}\n" if self.surrounding_heading else ""
        section = f"Section: {self.section_path}\n" if self.section_path else ""
        return f"{section}{heading}Source: {self.file_name}\nText:\n{self.text}"

    def metadata(self) -> dict:
        return {
            "block_id": self.block_id,
            "source_path": self.source_path,
            "file_name": self.file_name,
            "block_index": self.block_index,
            "surrounding_heading": self.surrounding_heading,
            "section_path": self.section_path,
            "retrieval_granularity": "docling_text",
            "content_hash": sha256_text(self.text),
        }


def convert_pdf_with_docling(pdf_path: Path, output_dir: Path) -> dict:
    from docling.document_converter import DocumentConverter

    output_dir.mkdir(parents=True, exist_ok=True)
    converter = DocumentConverter()
    result = converter.convert(str(pdf_path))
    document = result.document

    markdown = document.export_to_markdown()
    markdown_path = output_dir / f"{pdf_path.stem}.md"
    markdown_path.write_text(markdown, encoding="utf-8")

    json_path = output_dir / f"{pdf_path.stem}.json"
    export_payload = None
    for attr in ("export_to_dict", "model_dump", "dict"):
        if hasattr(document, attr):
            try:
                export_payload = getattr(document, attr)()
                break
            except TypeError:
                continue
    if export_payload is not None:
        json_path.write_text(
            json.dumps(export_payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    return {
        "pdf_path": str(pdf_path),
        "markdown_path": str(markdown_path),
        "json_path": str(json_path) if export_payload is not None else None,
        "markdown_chars": len(markdown),
    }


def is_markdown_table_separator(line: str) -> bool:
    stripped = line.strip()
    if "|" not in stripped:
        return False
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)


def is_markdown_table_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def split_markdown_table_row(line: str) -> list[str]:
    return [clean_cell(cell) for cell in line.strip().strip("|").split("|")]


def unique_headers(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    normalized: list[str] = []
    for idx, header in enumerate(headers):
        base = header or f"column_{idx + 1}"
        count = seen.get(base, 0)
        seen[base] = count + 1
        normalized.append(base if count == 0 else f"{base}_{count + 1}")
    return normalized


def table_headers_and_row_labels(markdown: str) -> tuple[list[str], list[str]]:
    lines = [line for line in markdown.splitlines() if is_markdown_table_line(line)]
    if len(lines) < 3:
        return [], []
    headers = unique_headers(split_markdown_table_row(lines[0]))
    row_labels = []
    for line in lines[2:]:
        values = split_markdown_table_row(line)
        label = next((value for value in values if value), "")
        if label:
            row_labels.append(label)
    return headers, row_labels


def table_profile(markdown: str) -> str:
    headers, row_labels = table_headers_and_row_labels(markdown)
    parts = []
    if headers:
        parts.append(f"columns={', '.join(headers[:12])}")
    if row_labels:
        parts.append(f"rows={len(row_labels)}")
        parts.append(f"row_labels={', '.join(row_labels[:8])}")
    return "; ".join(parts) if parts else "unstructured table"


def extract_rows_from_table(table: ExtractedTable) -> list[ExtractedTableRow]:
    lines = [line for line in table.markdown.splitlines() if is_markdown_table_line(line)]
    if len(lines) < 3:
        return []

    headers = unique_headers(split_markdown_table_row(lines[0]))
    rows: list[ExtractedTableRow] = []
    for markdown_row_index, line in enumerate(lines[2:]):
        values = split_markdown_table_row(line)
        if not any(values):
            continue
        cells = {
            header: values[idx] if idx < len(values) else ""
            for idx, header in enumerate(headers)
        }
        row_label = next((value for value in values if value), "")
        row_id = sha256_text(
            f"{table.source_path}:{table.table_index}:{markdown_row_index}:{json.dumps(cells, sort_keys=True)}"
        )[:24]
        rows.append(
            ExtractedTableRow(
                row_id=row_id,
                table_id=table.table_id,
                source_path=table.source_path,
                file_name=table.file_name,
                table_index=table.table_index,
                row_index=markdown_row_index,
                row_label=row_label,
                cells=cells,
                surrounding_heading=table.surrounding_heading,
                section_path=table.section_path,
            )
        )
    return rows


def expand_tables_with_rows(tables: list[ExtractedTable]) -> list[ExtractedTable | ExtractedTableRow]:
    records: list[ExtractedTable | ExtractedTableRow] = []
    for table in tables:
        records.append(table)
        records.extend(extract_rows_from_table(table))
    return records


def text_block_is_useful(text: str) -> bool:
    if len(text) < 80:
        return False
    has_number = bool(re.search(r"\d|\$|%", text))
    has_finance_term = bool(
        re.search(
            r"repurchas|inventor|expense|sales|revenue|income|cash|assets|liabilities|"
            r"margin|quarter|fiscal|store|capital|depreciation|amortization",
            text,
            re.I,
        )
    )
    return has_number and has_finance_term


def extract_markdown_text_blocks(
    markdown: str,
    *,
    source_path: str,
    repeated_lines: set[str] | None = None,
) -> list[ExtractedTextBlock]:
    blocks: list[ExtractedTextBlock] = []
    current: list[str] = []
    last_heading = ""
    heading_stack: list[tuple[int, str]] = []
    in_table = False
    repeated_lines = repeated_lines or set()

    def flush() -> None:
        if not current:
            return
        text = clean_cell(" ".join(current))
        current.clear()
        if not text_block_is_useful(text):
            return
        block_index = len(blocks)
        path = Path(source_path)
        block_id = sha256_text(f"{source_path}:text:{block_index}:{sha256_text(text)}")[:24]
        blocks.append(
            ExtractedTextBlock(
                block_id=block_id,
                source_path=source_path,
                file_name=path.name,
                block_index=block_index,
                text=text,
                surrounding_heading=last_heading,
                section_path=section_path_from_stack(heading_stack),
            )
        )

    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            flush()
            in_table = False
            continue
        if stripped.startswith("#"):
            flush()
            heading_stack = update_heading_stack(heading_stack, stripped)
            last_heading = heading_text(stripped)
            continue
        if is_markdown_table_line(stripped) or is_markdown_table_separator(stripped):
            flush()
            in_table = True
            continue
        if in_table:
            continue
        if is_repeated_noise_line(stripped, repeated_lines):
            continue
        current.append(stripped)
    flush()
    return blocks


def extract_markdown_tables(markdown: str, *, source_path: str) -> list[ExtractedTable]:
    lines = markdown.splitlines()
    tables: list[ExtractedTable] = []
    idx = 0
    last_heading = ""
    heading_stack: list[tuple[int, str]] = []

    while idx < len(lines):
        line = lines[idx]
        if line.lstrip().startswith("#"):
            heading_stack = update_heading_stack(heading_stack, line)
            last_heading = heading_text(line)

        if (
            idx + 1 < len(lines)
            and is_markdown_table_line(lines[idx])
            and is_markdown_table_separator(lines[idx + 1])
        ):
            start = idx
            idx += 2
            while idx < len(lines) and is_markdown_table_line(lines[idx]):
                idx += 1
            table_markdown = "\n".join(lines[start:idx]).strip()
            if table_markdown:
                table_index = len(tables)
                table_id = sha256_text(f"{source_path}:{table_index}:{sha256_text(table_markdown)}")[:24]
                path = Path(source_path)
                tables.append(
                    ExtractedTable(
                        table_id=table_id,
                        source_path=source_path,
                        file_name=path.name,
                        table_index=table_index,
                        markdown=table_markdown,
                        surrounding_heading=last_heading,
                        section_path=section_path_from_stack(heading_stack),
                    )
                )
            continue
        idx += 1

    return tables


def parse_docling_markdown_tables(markdown_dir: Path, pdf_dir: Path) -> list[ExtractedTable]:
    tables: list[ExtractedTable] = []
    for markdown_path in sorted(markdown_dir.glob("*.md")):
        pdf_path = pdf_dir / f"{markdown_path.stem}.pdf"
        source_path = str(pdf_path if pdf_path.exists() else markdown_path)
        markdown = markdown_path.read_text(encoding="utf-8")
        tables.extend(extract_markdown_tables(markdown, source_path=source_path))
    return tables


def parse_docling_markdown_text_blocks(markdown_dir: Path, pdf_dir: Path) -> list[ExtractedTextBlock]:
    blocks: list[ExtractedTextBlock] = []
    for markdown_path in sorted(markdown_dir.glob("*.md")):
        pdf_path = pdf_dir / f"{markdown_path.stem}.pdf"
        source_path = str(pdf_path if pdf_path.exists() else markdown_path)
        markdown = markdown_path.read_text(encoding="utf-8")
        repeated_lines = build_repeated_line_filter(markdown)
        blocks.extend(
            extract_markdown_text_blocks(
                markdown,
                source_path=source_path,
                repeated_lines=repeated_lines,
            )
        )
    return blocks


def build_table_index(
    tables: list[ExtractedTable],
    *,
    text_blocks: list[ExtractedTextBlock] | None = None,
    reset: bool = True,
    batch_size: int = 16,
    include_rows: bool = True,
) -> dict:
    collection = get_table_chroma_collection(reset=reset)
    records = expand_tables_with_rows(tables) if include_rows else list(tables)
    records.extend(text_blocks or [])
    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        texts = [record.retrieval_text for record in batch]
        embeddings = Settings.embed_model.get_text_embedding_batch(texts)
        collection.add(
            ids=[
                record.row_id
                if isinstance(record, ExtractedTableRow)
                else record.block_id
                if isinstance(record, ExtractedTextBlock)
                else record.table_id
                for record in batch
            ],
            documents=texts,
            metadatas=[record.metadata() for record in batch],
            embeddings=embeddings,
        )
        print(f"Indexed table records {start + len(batch)}/{len(records)}", flush=True)

    return {
        "table_count": len(tables),
        "table_row_count": sum(1 for record in records if isinstance(record, ExtractedTableRow)),
        "text_block_count": len(text_blocks or []),
        "indexed_record_count": len(records),
        "collection_count": collection.count(),
    }
