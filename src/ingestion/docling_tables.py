from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from llama_index.core import Settings

from src.retrieval.source_period import governance_metadata
from src.vector_store import get_table_chroma_collection

MarkdownTableRecord = "ExtractedTable | ExtractedTableRow"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("<br>", " ").strip())


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


@dataclass(slots=True)
class ExtractedTable:
    table_id: str
    source_path: str
    file_name: str
    table_index: int
    markdown: str
    surrounding_heading: str
    section_path: str = ""
    page_number: int | None = None

    @property
    def retrieval_text(self) -> str:
        heading = f"Heading: {self.surrounding_heading}\n" if self.surrounding_heading else ""
        section = f"Section: {self.section_path}\n" if self.section_path else ""
        profile = f"Table profile: {table_profile(self.markdown)}\n"
        return f"{section}{heading}Source: {self.file_name}\n{profile}Table:\n{self.markdown}"

    def metadata(self) -> dict:
        headers, row_labels = table_headers_and_row_labels(self.markdown)
        metadata = {
            "table_id": self.table_id,
            "parent_id": self.table_id,
            "parent_type": "table",
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
        if self.page_number is not None:
            metadata["page_number"] = self.page_number
            metadata["page_label"] = str(self.page_number)
        metadata.update(governance_metadata(metadata))
        return metadata


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
    page_number: int | None = None

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
        metadata = {
            "row_id": self.row_id,
            "table_id": self.table_id,
            "parent_id": self.table_id,
            "parent_type": "table",
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
        if self.page_number is not None:
            metadata["page_number"] = self.page_number
            metadata["page_label"] = str(self.page_number)
        metadata.update(governance_metadata(metadata))
        return metadata


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
                page_number=table.page_number,
            )
        )
    return rows


def expand_tables_with_rows(tables: list[ExtractedTable]) -> list[ExtractedTable | ExtractedTableRow]:
    records: list[ExtractedTable | ExtractedTableRow] = []
    for table in tables:
        records.append(table)
        records.extend(extract_rows_from_table(table))
    return records


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


def docling_table_page_numbers(document: dict) -> list[int | None]:
    """Return the physical PDF page for each Docling table in document order."""
    page_numbers: list[int | None] = []
    for table in document.get("tables", []):
        page_number = None
        for provenance in table.get("prov", []):
            value = provenance.get("page_no")
            if isinstance(value, int) and value > 0:
                page_number = value
                break
        page_numbers.append(page_number)
    return page_numbers


def load_docling_table_page_numbers(json_path: Path) -> list[int | None]:
    if not json_path.exists():
        return []
    return docling_table_page_numbers(json.loads(json_path.read_text(encoding="utf-8")))


def parse_docling_markdown_tables(markdown_dir: Path, pdf_dir: Path) -> list[ExtractedTable]:
    tables: list[ExtractedTable] = []
    for markdown_path in sorted(markdown_dir.glob("*.md")):
        pdf_path = pdf_dir / f"{markdown_path.stem}.pdf"
        source_path = str(pdf_path if pdf_path.exists() else markdown_path)
        markdown = markdown_path.read_text(encoding="utf-8")
        document_tables = extract_markdown_tables(markdown, source_path=source_path)
        page_numbers = load_docling_table_page_numbers(markdown_path.with_suffix(".json"))
        for table, page_number in zip(document_tables, page_numbers):
            table.page_number = page_number
        tables.extend(document_tables)
    return tables


def build_table_index(
    tables: list[ExtractedTable],
    *,
    reset: bool = True,
    batch_size: int = 128,
) -> dict:
    collection = get_table_chroma_collection(reset=reset)
    records = expand_tables_with_rows(tables)
    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        texts = [record.retrieval_text for record in batch]
        embeddings = Settings.embed_model.get_text_embedding_batch(texts)
        collection.add(
            ids=[
                record.row_id
                if isinstance(record, ExtractedTableRow)
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
        "indexed_record_count": len(records),
        "collection_count": collection.count(),
    }
