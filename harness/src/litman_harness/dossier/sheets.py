"""Google Sheets ranges of one dossier, edited through closed operations the person accepts.

The assistant proposes a short list of closed operations on explicit A1
ranges; the preview resolves ``append_rows`` into an explicit range, hashes
the current and expected values of every range and stores a plan.  The apply
re-checks membership and ``canEdit``, then writes each range only if its
current values still match the hash seen by the preview.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any

from ..adapters.sheets import FORMULA, SheetsGateway, UNFORMATTED_VALUE
from ..errors import HarnessError
from ..plans.models import Plan, PlanAction
from .membership import belongs_to_root, in_litman
from .models import GOOGLE_SHEET_MIME, Resource
from .service import ExpedienteService, OperationConflict, OperationRun

MAX_OPERATIONS = 20
MAX_CELLS = 5_000
OPERATIONS = {"update_range": ("range", "values"), "append_rows": ("sheet", "values")}
_CELL_TYPES = (str, int, float, bool, type(None))
_RANGE_RE = re.compile(r"^(?:'(?P<quoted>(?:[^']|'')*)'|(?P<bare>[^'!]+))!"
                       r"(?P<c1>[A-Z]+)(?P<r1>[0-9]+):(?P<c2>[A-Z]+)(?P<r2>[0-9]+)$")


def _col_index(letters: str) -> int:
    value = 0
    for char in letters:
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value


def _col_letters(index: int) -> str:
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def quoted_title(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"


@dataclass(frozen=True)
class SheetRange:
    """An explicit, closed A1 range: both edges are given row and column numbers, never open-ended."""
    title: str
    first_row: int
    first_col: int
    last_row: int
    last_col: int

    @property
    def rows(self) -> int:
        return self.last_row - self.first_row + 1

    @property
    def cols(self) -> int:
        return self.last_col - self.first_col + 1

    @property
    def a1(self) -> str:
        return (f"{quoted_title(self.title)}!{_col_letters(self.first_col)}{self.first_row}:"
                f"{_col_letters(self.last_col)}{self.last_row}")

    def overlaps(self, other: "SheetRange") -> bool:
        return (self.title == other.title and self.first_row <= other.last_row
                and other.first_row <= self.last_row and self.first_col <= other.last_col
                and other.first_col <= self.last_col)


def parse_range(value: Any) -> SheetRange:
    """An explicit ``'Hoja'!A1:B2`` range; open-ended forms (a whole row or column) are rejected."""
    match = _RANGE_RE.match(value) if isinstance(value, str) else None
    if not match:
        raise _invalid("range debe ser un rango explícito como 'Hoja'!A1:B2")
    title = (match["quoted"] or match["bare"]).replace("''", "'")
    first_row, last_row = int(match["r1"]), int(match["r2"])
    first_col, last_col = _col_index(match["c1"]), _col_index(match["c2"])
    if first_row < 1 or first_col < 1 or first_row > last_row or first_col > last_col:
        raise _invalid("range no es un rango válido")
    return SheetRange(title, first_row, first_col, last_row, last_col)


def _normalize_cell(value: Any) -> Any:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and float(value).is_integer():
        return int(value)
    return value


def normalized_matrix(values: list[list[Any]], rows: int, cols: int) -> list[list[Any]]:
    """Pad (or trim) ``values`` to exactly ``rows`` x ``cols``, with missing and empty cells as ``""``."""
    return [[_normalize_cell(values[r][c] if r < len(values) and c < len(values[r]) else None)
             for c in range(cols)] for r in range(rows)]


def matrix_sha256(matrix: list[list[Any]]) -> str:
    encoded = json.dumps(matrix, separators=(",", ":"), ensure_ascii=False)
    return sha256(encoded.encode("utf-8")).hexdigest()


def _invalid(message: str, **details: Any) -> HarnessError:
    return HarnessError("invalid_request", message, details=details)


def _checked_values(values: Any, index: int) -> list[list[Any]]:
    if not isinstance(values, list) or not values or not all(isinstance(row, list) and row for row in values):
        raise _invalid("values debe ser una matriz rectangular no vacía", operation=index)
    width = len(values[0])
    for row in values:
        if len(row) != width:
            raise _invalid("values debe ser una matriz rectangular (todas las filas con el mismo número de celdas)",
                           operation=index)
        for cell in row:
            if not isinstance(cell, _CELL_TYPES):
                raise _invalid("Las celdas deben ser texto, número, booleano o nulo", operation=index)
    return values


def validated_operations(operations: Any) -> list[dict[str, Any]]:
    """1–20 closed operations with exact fields; checked here because transports validate only top-level types."""
    if not isinstance(operations, list) or not 1 <= len(operations) <= MAX_OPERATIONS:
        raise _invalid(f"Indique entre 1 y {MAX_OPERATIONS} operaciones")
    clean = []
    for index, operation in enumerate(operations):
        kind = operation.get("op") if isinstance(operation, dict) else None
        if kind not in OPERATIONS:
            raise _invalid("Operación no admitida", operation=index, allowed=list(OPERATIONS))
        fields = OPERATIONS[kind]
        if set(operation) != {"op", *fields}:
            raise _invalid(f"La operación {kind} lleva exactamente los campos op, " + ", ".join(fields),
                           operation=index, fields=list(fields))
        values = _checked_values(operation["values"], index)
        if kind == "update_range":
            if not isinstance(operation["range"], str) or not operation["range"]:
                raise _invalid("range debe ser texto", operation=index)
            clean.append({"op": kind, "range": operation["range"], "values": values})
        else:
            if not isinstance(operation["sheet"], str) or not operation["sheet"]:
                raise _invalid("sheet debe ser texto", operation=index)
            clean.append({"op": kind, "sheet": operation["sheet"], "values": values})
    return clean


class SheetsService:
    def __init__(self, dossier: ExpedienteService, sheets: SheetsGateway):
        self.dossier = dossier
        self.drive = dossier.drive
        self.sheets = sheets

    # -- plan ------------------------------------------------------------------------------------

    def preview_edit(self, folder_id: str, spreadsheet_id: str, operations: list[dict[str, Any]]) -> dict[str, Any]:
        """Resolve closed operations against the current values and store a ``sheet_edit`` plan; writes nothing."""
        clean = validated_operations(operations)
        root = self.dossier.root(folder_id)
        account = self.dossier.account_id()
        item = self._resolve(root, spreadsheet_id)
        if not item.capabilities.get("canEdit"):
            raise HarnessError("insufficient_capability", "La cuenta no puede editar esta hoja de cálculo",
                               details={"spreadsheet_id": item.id})
        titles = self._titles(item.id)
        resolved, total_cells = self._resolve_ranges(item.id, clean, titles)
        if total_cells > MAX_CELLS:
            raise _invalid(f"Las operaciones no pueden superar {MAX_CELLS} celdas en total", cells=total_cells)
        self._reject_overlaps(resolved)
        current = self._current_values(item.id, [sheet_range.a1 for sheet_range, _ in resolved])
        actions, previews = [], []
        for (sheet_range, values), existing, operation in zip(resolved, current, clean):
            expected = normalized_matrix(values, sheet_range.rows, sheet_range.cols)
            before = normalized_matrix(existing, sheet_range.rows, sheet_range.cols)
            actions.append(PlanAction("write_range", item.id, sheet_range.a1, None, metadata={
                "range": sheet_range.a1, "values": expected, "before_sha256": matrix_sha256(before),
                "after_sha256": matrix_sha256(expected)}))
            previews.append({**operation, "range": sheet_range.a1})
        plan = Plan("sheet_edit", root.id, account, tuple(actions), {})
        self.dossier.store().save(plan)
        return {**plan.json(), "spreadsheet_id": item.id, "operations": previews}

    def apply_edit(self, accepted_plan_id: str) -> dict[str, Any]:
        return self.dossier.apply_plan(accepted_plan_id, "sheet_edit", self._run_edit)

    def _run_edit(self, run: OperationRun, root: Resource) -> dict[str, Any]:
        item = self._resolve(root, run.plan.actions[0].resource_id)
        if not item.capabilities.get("canEdit"):
            raise HarnessError("insufficient_capability", "La cuenta ya no puede editar esta hoja de cálculo",
                               details={"spreadsheet_id": item.id})
        for action in run.plan.actions:
            if not run.done(action):
                run.complete(action, self._write_range(item.id, action))
        return run.envelope("succeeded", writes=True, spreadsheet_id=item.id, name=item.name,
                            web_view_link=item.web_view_link)

    def _write_range(self, spreadsheet_id: str, action: PlanAction) -> dict[str, Any]:
        sheet_range = parse_range(action.metadata["range"])
        current = self._current_values(spreadsheet_id, [action.metadata["range"]])[0]
        current_hash = matrix_sha256(normalized_matrix(current, sheet_range.rows, sheet_range.cols))
        if current_hash == action.metadata["after_sha256"]:
            return {"written": False, "resumed": True}  # the write may have already happened (lost answer)
        if current_hash != action.metadata["before_sha256"]:
            raise OperationConflict("El rango cambió desde la vista previa", details={
                "code": "sheet_changed", "range": action.metadata["range"]})
        self.sheets.update(spreadsheet_id, action.metadata["range"], action.metadata["values"])
        return {"written": True}

    # -- resolution --------------------------------------------------------------------------------

    def _resolve_ranges(self, spreadsheet_id: str, operations: list[dict[str, Any]],
                        titles: set[str]) -> tuple[list[tuple[SheetRange, list[list[Any]]]], int]:
        resolved: list[tuple[SheetRange, list[list[Any]]]] = []
        next_row: dict[str, int] = {}
        total_cells = 0
        for index, operation in enumerate(operations):
            values = operation["values"]
            if operation["op"] == "update_range":
                sheet_range = parse_range(operation["range"])
                if sheet_range.title not in titles:
                    raise _invalid("La hoja indicada no existe", operation=index, sheet=sheet_range.title)
                if len(values) != sheet_range.rows or len(values[0]) != sheet_range.cols:
                    raise _invalid("values no tiene el tamaño del rango", operation=index)
            else:
                title = operation["sheet"]
                if title not in titles:
                    raise _invalid("La hoja indicada no existe", operation=index, sheet=title)
                start = next_row.get(title)
                if start is None:
                    start = self._first_empty_row(spreadsheet_id, title)
                cols = len(values[0])
                sheet_range = SheetRange(title, start, 1, start + len(values) - 1, cols)
                next_row[title] = sheet_range.last_row + 1
            total_cells += sheet_range.rows * sheet_range.cols
            resolved.append((sheet_range, values))
        return resolved, total_cells

    @staticmethod
    def _reject_overlaps(resolved: list[tuple[SheetRange, list[list[Any]]]]) -> None:
        for first in range(len(resolved)):
            for second in range(first + 1, len(resolved)):
                if resolved[first][0].overlaps(resolved[second][0]):
                    raise HarnessError("overlapping_operations", "Dos operaciones afectan al mismo rango",
                                       details={"operations": [first, second]})

    def _titles(self, spreadsheet_id: str) -> set[str]:
        sheets = self.sheets.get(spreadsheet_id).get("sheets") or []
        return {str((entry.get("properties") or {}).get("title") or "") for entry in sheets}

    def _first_empty_row(self, spreadsheet_id: str, title: str) -> int:
        rows = self.sheets.values(spreadsheet_id, [quoted_title(title)], FORMULA)[0].get("values") or []
        for index in range(len(rows) - 1, -1, -1):
            if any(cell not in (None, "") for cell in rows[index]):
                return index + 2
        return 1

    def _current_values(self, spreadsheet_id: str, ranges: list[str]) -> list[list[list[Any]]]:
        by_range = {}
        for entry in self.sheets.values(spreadsheet_id, ranges, UNFORMATTED_VALUE):
            value_range = entry.get("range")
            if isinstance(value_range, str):
                try:
                    value_range = parse_range(value_range).a1
                except HarnessError:
                    pass
            by_range[value_range] = entry.get("values") or []
        return [by_range.get(parse_range(a1).a1, []) for a1 in ranges]

    # -- shared helpers ------------------------------------------------------------------------------

    def _resolve(self, root: Resource, spreadsheet_id: str) -> Resource:
        """A Google Sheet inside the tree and not below ``_LitMan``, proved before any Sheets call."""
        item = self.drive.get(spreadsheet_id)
        if not belongs_to_root(self.drive, root, item) or in_litman(self.drive, root, item):
            raise HarnessError("document_outside_tree", "La hoja de cálculo no está dentro de la licitación "
                               "conectada", details={"spreadsheet_id": spreadsheet_id})
        if item.mime_type != GOOGLE_SHEET_MIME:
            raise HarnessError("unsupported_document", "Sólo se pueden editar hojas de cálculo de Google Sheets; "
                               "conviértala primero", details={"mime_type": item.mime_type})
        return item
