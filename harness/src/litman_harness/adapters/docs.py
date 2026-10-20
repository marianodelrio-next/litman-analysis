"""Personal OAuth Google Docs adapter: read one document and send one guarded batch of edits."""
from __future__ import annotations

import json
from typing import Any, Protocol

from ..errors import HarnessError

# Enough to count the tabs and read the first tab's body; never headers, footers or styles.
_FIELDS = ("revisionId,suggestionsViewMode,"
           "tabs(tabProperties(tabId),childTabs(tabProperties(tabId)),documentTab(body))")
_DISABLED_REASONS = {"accessNotConfigured", "SERVICE_DISABLED"}


class DocsGateway(Protocol):
    def get(self, document_id: str) -> dict[str, Any]: ...
    def batch_update(self, document_id: str, requests: list[dict[str, Any]],
                     required_revision_id: str) -> dict[str, Any]: ...


_HTTP_ERRORS = {
    401: ("oauth_login_required", "La sesión de Google no es válida; ejecute `litman login`"),
    403: ("insufficient_permission", "La cuenta o la aplicación no tienen permiso para este documento de Google Docs"),
    404: ("not_found", "El documento de Google Docs no existe o la aplicación no tiene acceso a él"),
}


def _reasons(content: Any) -> set[str]:
    """``error.errors[].reason`` and ``error.details[].reason`` of a Google API error body."""
    try:
        error = json.loads(content.decode("utf-8") if isinstance(content, bytes) else content)["error"]
    except (AttributeError, KeyError, TypeError, ValueError):
        return set()
    if not isinstance(error, dict):
        return set()
    items = [*(error.get("errors") or []), *(error.get("details") or [])]
    return {item["reason"] for item in items if isinstance(item, dict) and isinstance(item.get("reason"), str)}


def docs_http_error(status: int, content: Any = None, *, write: bool = False) -> HarnessError:
    """The stable harness error for a failed Google Docs HTTP response.

    A 400 on a write carries ``requiredRevisionId``: the document changed after the preview.
    """
    if status == 403 and _reasons(content) & _DISABLED_REASONS:
        return HarnessError("docs_api_disabled",
                            "La API de Google Docs no está habilitada: el administrador debe habilitar la Google Docs "
                            "API en el proyecto de Google Cloud del cliente OAuth",
                            details={"http_status": status})
    if status == 400 and write:
        return HarnessError("document_changed", "El documento cambió desde la vista previa; prepare un plan nuevo",
                            details={"http_status": status})
    code, message = _HTTP_ERRORS.get(status, ("docs_error", "Google Docs rechazó la solicitud"))
    return HarnessError(code, message, details={"http_status": status})


def _execute(request: Any, *, write: bool = False) -> Any:
    from googleapiclient.errors import HttpError
    try:
        return request.execute()
    except HttpError as exc:
        raise docs_http_error(int(getattr(exc.resp, "status", 0) or 0), exc.content, write=write) from exc


class GoogleDocsGateway:
    """Narrow Docs v1 adapter; the dossier service decides which documents it may touch."""

    def __init__(self, service: Any):
        self.service = service

    def get(self, document_id: str) -> dict[str, Any]:
        # Suggestions inline so that every index matches the document the batch is applied to.
        return _execute(self.service.documents().get(documentId=document_id, includeTabsContent=True,
                                                     suggestionsViewMode="SUGGESTIONS_INLINE", fields=_FIELDS))

    def batch_update(self, document_id: str, requests: list[dict[str, Any]],
                     required_revision_id: str) -> dict[str, Any]:
        body = {"requests": requests, "writeControl": {"requiredRevisionId": required_revision_id}}
        return _execute(self.service.documents().batchUpdate(documentId=document_id, body=body), write=True)
