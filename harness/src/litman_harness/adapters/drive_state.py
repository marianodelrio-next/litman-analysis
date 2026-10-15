"""Shared dossier state on Drive with a real compare-and-swap (Drive API v2 ``If-Match``).

The authorized smoke of 2026-10-15 showed that a v2 media update with the
current ETag succeeds and with a stale one returns 412 (strong ETag), while v3
exposes no ETag.  The only version token of shared state is therefore the v2
ETag returned by ``read``.  Raw HTTP goes through an injectable authorized
session (``google.auth.transport.requests.AuthorizedSession`` in production).
"""
from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from ..dossier.models import ACTION_MARKER, OPERATION_MARKER, Resource
from ..errors import HarnessError
from .drive import DriveGateway, http_error

V2_FILE = "https://www.googleapis.com/drive/v2/files/{file_id}"
V3_FILE = "https://www.googleapis.com/drive/v3/files/{file_id}"
V2_UPLOAD = "https://www.googleapis.com/upload/drive/v2/files/{file_id}"
V3_CREATE = "https://www.googleapis.com/upload/drive/v3/files"
_ALL_DRIVES = {"supportsAllDrives": "true"}
READ_ATTEMPTS = 3


def mime_for(name: str) -> str:
    if name.endswith(".json"):
        return "application/json"
    if name.endswith(".md"):
        return "text/markdown"
    return "text/plain"


class DriveSharedState:
    """``SharedStateCapability`` for Drive: coherent read, CAS update and marked creation."""
    available = True

    def __init__(self, session: Any, drive: DriveGateway):
        self.session = session
        self.drive = drive

    def read(self, file_id: str) -> tuple[str, str]:
        """``(content, etag)`` of one coherent snapshot: the ETag is the same before and after."""
        for _ in range(READ_ATTEMPTS):
            before = self._etag(file_id)
            content = self._request("GET", V3_FILE.format(file_id=file_id),
                                    params={"alt": "media", **_ALL_DRIVES}).content
            if self._etag(file_id) == before:
                try:
                    return content.decode("utf-8"), before
                except UnicodeDecodeError as exc:
                    raise HarnessError("invalid_shared_state", "El estado compartido no es UTF-8",
                                       details={"file_id": file_id}) from exc
        raise HarnessError("concurrent_change", "El archivo cambia mientras se lee", details={"file_id": file_id})

    def update_if_version(self, file_id: str, content: str, expected_version: str, operation_id: str) -> Resource:
        """Replace only the content, and only if the ETag is still ``expected_version``."""
        current = self.drive.get(file_id)
        response = self.session.request(
            "PUT", V2_UPLOAD.format(file_id=file_id), params={"uploadType": "media", **_ALL_DRIVES},
            headers={"If-Match": expected_version, "Content-Type": mime_for(current.name)},
            data=content.encode("utf-8"))
        if response.status_code == 412:
            raise HarnessError("concurrent_change", "Otra persona cambió el archivo; no se sobrescribe",
                               details={"file_id": file_id})
        self._check(response)
        return self.drive.get(file_id)

    def create_if_absent(self, name: str, parent_id: str, content: str, operation_id: str,
                         action_id: str) -> Resource:
        """Adopt the file this action already created, refuse an existing name, or create it.

        Not atomic across different operations: two simultaneous creations surface
        later as ``manifest_duplicated`` and need human repair (accepted risk).
        """
        marked = self.drive.find_by_markers(parent_id, operation_id, action_id)
        if len(marked) > 1:
            raise HarnessError("concurrent_change", "Hay varios archivos con los marcadores de la misma acción",
                               details={"candidates": [item.id for item in marked]})
        if marked:
            return marked[0]
        parent = self.drive.get(parent_id)
        existing = [item for item in self.drive.children(parent_id, parent.drive_id) if item.name == name]
        if existing:
            raise HarnessError("already_exists", "Ya existe un archivo con ese nombre; no se sobrescribe",
                               details={"file_id": existing[0].id})
        metadata = {"name": name, "parents": [parent_id], "mimeType": mime_for(name),
                    "appProperties": {OPERATION_MARKER: operation_id, ACTION_MARKER: action_id}}
        boundary = f"litman-{uuid4().hex}"
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(metadata)}\r\n"
                f"--{boundary}\r\nContent-Type: {mime_for(name)}; charset=UTF-8\r\n\r\n{content}\r\n"
                f"--{boundary}--\r\n").encode("utf-8")
        response = self._request("POST", V3_CREATE, params={"uploadType": "multipart", "fields": "id", **_ALL_DRIVES},
                                 headers={"Content-Type": f"multipart/related; boundary={boundary}"}, data=body)
        return self.drive.get(response.json()["id"])

    def _etag(self, file_id: str) -> str:
        etag = self._request("GET", V2_FILE.format(file_id=file_id),
                             params={"fields": "etag", **_ALL_DRIVES}).json().get("etag")
        if not isinstance(etag, str) or not etag:
            raise HarnessError("drive_error", "Drive no devolvió ETag del estado compartido",
                               details={"file_id": file_id})
        return etag

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        response = self.session.request(method, url, **kwargs)
        self._check(response)
        return response

    @staticmethod
    def _check(response: Any) -> None:
        if response.status_code >= 400:
            raise http_error(response.status_code)
