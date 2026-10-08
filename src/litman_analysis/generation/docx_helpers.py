"""Small presentation-only helpers shared by deterministic DOCX renderers."""
from __future__ import annotations

from typing import Any, Callable

from docx import Document

MISSING = "No consta"


def boolean_value(value: Any) -> str:
    return "Sí" if value is True else "No" if value is False else MISSING


def display_value(value: Any) -> str:
    if value is None or value == "" or value == {} or value == []:
        return MISSING
    if isinstance(value, bool):
        return boolean_value(value)
    if isinstance(value, (list, tuple)):
        return join_values(value)
    if isinstance(value, dict):
        return named_description(value)
    return str(value)


def join_values(values: Any) -> str:
    return "; ".join(display_value(value) for value in values) if isinstance(values, list) and values else MISSING


def named_description(value: Any) -> str:
    if not isinstance(value, dict):
        return display_value(value)
    name, description = display_value(value.get("nombre")), display_value(value.get("descripcion"))
    return name if description == MISSING else f"{name} — {description}"


def amount_value(value: Any, currency: Any) -> str:
    return MISSING if value is None else f"{value} {currency}" if currency not in (None, "") else str(value)


def truncate_value(value: Any, limit: int = 500) -> str:
    text = display_value(value)
    return text if len(text) <= limit else text[:limit - 1] + "…"


def add_table(doc: Document, headers: list[str], rows: list[tuple[Any, ...]]) -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for cell, value in zip(table.rows[0].cells, headers):
        cell.text = str(value)
    for values in rows:
        for cell, value in zip(table.add_row().cells, values):
            cell.text = display_value(value)


def add_table_or_missing(doc: Document, headers: list[str], values: Any,
                         row: Callable[[dict[str, Any]], tuple[Any, ...]]) -> None:
    rows = [row(item) for item in values if isinstance(item, dict)] if isinstance(values, list) else []
    add_table(doc, headers, rows or [tuple(MISSING for _ in headers)])
