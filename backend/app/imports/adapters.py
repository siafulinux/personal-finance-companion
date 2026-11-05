"""Import adapter architecture.

Phase 1 ships CSV. Future provider adapters (Plaid, SimpleFIN, etc.) implement the
same interface and populate the same ``TransactionImport`` records, so the review,
duplicate-detection and bill-matching pipeline stays unchanged.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.imports.parse import CsvDocument, ParsedRow, build_rows, parse_csv, suggest_mapping


@dataclass
class AdapterPreview:
    document: CsvDocument
    mapping: dict[str, str | None]
    suggested_mapping: dict[str, str | None]
    rows: list[ParsedRow]


class ImportAdapter(ABC):
    """Contract every import source must satisfy."""

    name: str

    @abstractmethod
    def read(self, content: bytes) -> CsvDocument: ...

    @abstractmethod
    def suggest_mapping(self, document: CsvDocument) -> dict[str, str | None]: ...

    @abstractmethod
    def preview(
        self, document: CsvDocument, mapping: dict[str, str | None] | None = None
    ) -> AdapterPreview: ...


class CsvImportAdapter(ImportAdapter):
    name = "csv"

    def read(self, content: bytes) -> CsvDocument:
        return parse_csv(content)

    def suggest_mapping(self, document: CsvDocument) -> dict[str, str | None]:
        return suggest_mapping(document.headers)

    def preview(
        self, document: CsvDocument, mapping: dict[str, str | None] | None = None
    ) -> AdapterPreview:
        suggested = suggest_mapping(document.headers)
        effective = {**suggested, **(mapping or {})}
        rows = build_rows(document, effective)
        return AdapterPreview(
            document=document,
            mapping=effective,
            suggested_mapping=suggested,
            rows=rows,
        )


_ADAPTERS: dict[str, ImportAdapter] = {"csv": CsvImportAdapter()}


def get_adapter(name: str = "csv") -> ImportAdapter:
    adapter = _ADAPTERS.get(name)
    if adapter is None:
        raise ValueError(f"Unknown import adapter: {name}")
    return adapter


def register_adapter(adapter: ImportAdapter) -> None:
    _ADAPTERS[adapter.name] = adapter
