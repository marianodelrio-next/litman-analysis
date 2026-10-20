"""Personal OAuth Google Sheets adapter: read the structure and the values of one spreadsheet."""
from __future__ import annotations

from typing import Any, Protocol

from ..errors import HarnessError
from .google_errors import reasons

_FIELDS = "sheets(properties(sheetId,title,gridProperties(rowCount,columnCount)))"
_DISABLED_REASONS = {"accessNotConfigured", "SERVICE_DISABLED"}
FORMATTED_VALUE = "FORMATTED_VALUE"
UNFORMATTED_VALUE = "UNFORMATTED_VALUE"
RAW = "RAW"


class SheetsGateway(Protocol):
    def get(self, spreadsheet_id: str) -> dict[str, Any]: ...
    def values(self, spreadsheet_id: str, ranges: list[str],
               render: str = FORMATTED_VALUE) -> list[dict[str, Any]]: ...
    def update(self, spreadsheet_id: str, range_: str, values: list[list[Any]]) -> dict[str, Any]: ...


_HTTP_ERRORS = {
    401: ("oauth_login_required", "La sesión de Google no es válida; ejecute `litman login`"),
    403: ("insufficient_permission", "La cuenta o la aplicación no tienen permiso para esta hoja de cálculo"),
    404: ("not_found", "La hoja de cálculo no existe o la aplicación no tiene acceso a ella"),
}


def sheets_http_error(status: int, content: Any = None) -> HarnessError:
    """The stable harness error for a failed Google Sheets HTTP response."""
    if status == 403 and reasons(content) & _DISABLED_REASONS:
        return HarnessError("sheets_api_disabled",
                            "La API de Google Sheets no está habilitada: el administrador debe habilitar la Google "
                            "Sheets API en el proyecto de Google Cloud del cliente OAuth",
                            details={"http_status": status})
    code, message = _HTTP_ERRORS.get(status, ("sheets_error", "Google Sheets rechazó la solicitud"))
    return HarnessError(code, message, details={"http_status": status})


def _execute(request: Any) -> Any:
    from googleapiclient.errors import HttpError
    try:
        return request.execute()
    except HttpError as exc:
        raise sheets_http_error(int(getattr(exc.resp, "status", 0) or 0), exc.content) from exc


class GoogleSheetsGateway:
    """Narrow Sheets v4 adapter; the dossier service decides which spreadsheets it may touch."""

    def __init__(self, service: Any):
        self.service = service

    def get(self, spreadsheet_id: str) -> dict[str, Any]:
        """Sheet titles and grid sizes only, so the size can be checked before any value is read."""
        return _execute(self.service.spreadsheets().get(spreadsheetId=spreadsheet_id, fields=_FIELDS))

    def values(self, spreadsheet_id: str, ranges: list[str], render: str = FORMATTED_VALUE) -> list[dict[str, Any]]:
        response = _execute(self.service.spreadsheets().values().batchGet(
            spreadsheetId=spreadsheet_id, ranges=ranges, valueRenderOption=render))
        return [item for item in response.get("valueRanges", []) if isinstance(item, dict)]

    def update(self, spreadsheet_id: str, range_: str, values: list[list[Any]]) -> dict[str, Any]:
        body = {"range": range_, "values": values}
        return _execute(self.service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=range_, valueInputOption=RAW, body=body))
