"""Google Sheets of the dossier: edit explicit ranges through closed operations, as the person accepts."""
from __future__ import annotations

from . import Tool, schema
from ...dossier.sheets import MAX_CELLS, MAX_OPERATIONS, OPERATIONS
from .dossier import _FOLDER_ID, _GATE, _PLAN_ID

_SPREADSHEET_ID = {"type": "string", "description": "ID de un Google Sheet dentro de la carpeta de la licitación."}
_CELL = {"description": "Valor de la celda: texto, número, booleano o null para una celda vacía."}
_OPERATION = {
    "type": "object", "required": ["op"], "additionalProperties": False,
    "properties": {
        "op": {"type": "string", "enum": list(OPERATIONS)},
        "range": {"type": "string", "description": "update_range: rango explícito, p. ej. 'Hoja 1'!A1:B2."},
        "sheet": {"type": "string", "description": "append_rows: título de la hoja donde añadir filas."},
        "values": {"type": "array", "minItems": 1, "items": {"type": "array", "minItems": 1, "items": _CELL},
                   "description": "Matriz rectangular de celdas; update_range exige el tamaño exacto del rango. "
                                  "null es una celda vacía."}}}

TOOLS = (
    Tool("preview_sheet_edit",
         "Consulta (no escribe en Drive): resuelve sobre los valores actuales de un Google Sheet de la licitación "
         f"hasta {MAX_OPERATIONS} operaciones cerradas (update_range, append_rows) y guarda localmente un plan con "
         f"el rango resuelto de cada operación, que la persona debe aceptar. Como máximo {MAX_CELLS} celdas en "
         "total; rechaza rangos superpuestos y hojas que no existen.",
         schema({"folder_id": _FOLDER_ID, "spreadsheet_id": _SPREADSHEET_ID,
                 "operations": {"type": "array", "minItems": 1, "maxItems": MAX_OPERATIONS, "items": _OPERATION}},
                ("folder_id", "spreadsheet_id", "operations")),
         lambda ctx, args: ctx.services().sheet_edits.preview_edit(args["folder_id"], args["spreadsheet_id"],
                                                                   args["operations"])),
    Tool("apply_sheet_edit",
         "Mutación: aplica sólo el plan_id de edición de hoja guardado y aceptado; si un rango cambió desde la "
         "vista previa devuelve conflict (sheet_changed) sin escribir ese rango." + _GATE,
         schema({"plan_id": _PLAN_ID}, ("plan_id",)),
         lambda ctx, args: ctx.services().sheet_edits.apply_edit(args["plan_id"]),
         mutates=True, destructive=True),
)
