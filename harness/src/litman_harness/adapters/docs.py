"""Personal OAuth Google Docs adapter: read one document and send one guarded batch of edits."""
from __future__ import annotations

import json
from typing import Any, Protocol

from ..errors import HarnessError
from .google_errors import reasons

# Enough to count the tabs and read the first tab's body; never headers, footers or styles.
_FIELDS = ("revisionId,suggestionsViewMode,"
           "tabs(tabProperties(tabId),childTabs(tabProperties(tabId)),documentTab(body))")
# The same, plus the document's comment threads and the first tab's comment anchors.
_COMMENT_FIELDS = ("revisionId,suggestionsViewMode,comments,"
                   "tabs(tabProperties(tabId),childTabs(tabProperties(tabId)),documentTab(body,commentAnchors))")
_DISABLED_REASONS = {"accessNotConfigured", "SERVICE_DISABLED"}


class DocsGateway(Protocol):
    def get(self, document_id: str) -> dict[str, Any]: ...
    def get_with_comments(self, document_id: str) -> dict[str, Any]: ...
    def batch_update(self, document_id: str, requests: list[dict[str, Any]],
                     required_revision_id: str) -> dict[str, Any]: ...
    def batch_update_comments(self, document_id: str, requests: list[dict[str, Any]],
                              required_revision_id: str) -> dict[str, Any]: ...


_HTTP_ERRORS = {
    401: ("oauth_login_required", "La sesión de Google no es válida; ejecute `litman login`"),
    403: ("insufficient_permission", "La cuenta o la aplicación no tienen permiso para este documento de Google Docs"),
    404: ("not_found", "El documento de Google Docs no existe o la aplicación no tiene acceso a él"),
}


def _stale_revision(content: Any) -> bool:
    """Whether a 400 body blames the required revision rather than the requests themselves."""
    try:
        error = json.loads(content.decode("utf-8") if isinstance(content, bytes) else content)["error"]
    except (AttributeError, KeyError, TypeError, ValueError):
        return False
    if not isinstance(error, dict):
        return False
    message = error.get("message")
    return error.get("status") == "FAILED_PRECONDITION" or (isinstance(message, str) and "revision" in message.lower())


def docs_http_error(status: int, content: Any = None, *, write: bool = False, comments: bool = False) -> HarnessError:
    """The stable harness error for a failed Google Docs HTTP response.

    A 400 on a write carries ``requiredRevisionId``: the document changed after the preview.  A comment batch
    (``comments``) is told apart: only a 400 that blames the revision is ``document_changed``; any other 400 is
    ``docs_request_rejected``, a request Google refused without writing anything.
    """
    if status == 403 and reasons(content) & _DISABLED_REASONS:
        return HarnessError("docs_api_disabled",
                            "La API de Google Docs no está habilitada: el administrador debe habilitar la Google Docs "
                            "API en el proyecto de Google Cloud del cliente OAuth",
                            details={"http_status": status})
    if status == 400 and comments and not _stale_revision(content):
        return HarnessError("docs_request_rejected", "Google Docs rechazó la solicitud de comentarios sin aplicarla",
                            details={"http_status": status})
    if status == 400 and write:
        return HarnessError("document_changed", "El documento cambió desde la vista previa; prepare un plan nuevo",
                            details={"http_status": status})
    code, message = _HTTP_ERRORS.get(status, ("docs_error", "Google Docs rechazó la solicitud"))
    return HarnessError(code, message, details={"http_status": status})


def _execute(request: Any, *, write: bool = False, comments: bool = False) -> Any:
    from googleapiclient.errors import HttpError
    try:
        return request.execute()
    except HttpError as exc:
        raise docs_http_error(int(getattr(exc.resp, "status", 0) or 0), exc.content, write=write,
                              comments=comments) from exc


class GoogleDocsGateway:
    """Narrow Docs v1 adapter; the dossier service decides which documents it may touch."""

    def __init__(self, service: Any):
        self.service = service

    def get(self, document_id: str) -> dict[str, Any]:
        # Suggestions inline so that every index matches the document the batch is applied to.
        return _execute(self.service.documents().get(documentId=document_id, includeTabsContent=True,
                                                     suggestionsViewMode="SUGGESTIONS_INLINE", fields=_FIELDS))

    def get_with_comments(self, document_id: str) -> dict[str, Any]:
        """The document with its native comment threads and anchors; asked only where comments are needed."""
        return _execute(self.service.documents().get(documentId=document_id, includeTabsContent=True,
                                                     suggestionsViewMode="SUGGESTIONS_INLINE",
                                                     commentsViewMode="COMMENTS_VIEW_MODE_INCLUDED",
                                                     fields=_COMMENT_FIELDS))

    def batch_update(self, document_id: str, requests: list[dict[str, Any]],
                     required_revision_id: str) -> dict[str, Any]:
        body = {"requests": requests, "writeControl": {"requiredRevisionId": required_revision_id}}
        return _execute(self.service.documents().batchUpdate(documentId=document_id, body=body), write=True)

    def batch_update_comments(self, document_id: str, requests: list[dict[str, Any]],
                              required_revision_id: str) -> dict[str, Any]:
        """One revision-guarded batch of native comment requests; the full response carries the save state."""
        body = {"requests": requests, "writeControl": {"requiredRevisionId": required_revision_id}}
        return _execute(self.service.documents().batchUpdate(documentId=document_id, body=body), write=True,
                        comments=True)
