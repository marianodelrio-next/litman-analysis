"""Personal OAuth Drive adapter and the gateway protocol used by services."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from ..dossier.models import ACTION_MARKER, FOLDER_MIME, GOOGLE_DOC_MIME, OPERATION_MARKER, Resource
from ..errors import HarnessError

_OPTIONS = {"supportsAllDrives": True}
# Only the capabilities the harness checks: keeps responses small for chat agents.
_CAPABILITIES = ("capabilities(canListChildren,canAddChildren,canDownload,canEdit,canMoveItemWithinDrive,"
                 "canCopy)")
_FIELDS = f"id,name,mimeType,version,size,driveId,parents,trashed,{_CAPABILITIES},webViewLink,appProperties,md5Checksum"


class DriveGateway(Protocol):
    def about(self) -> dict[str, Any]: ...
    def get(self, file_id: str) -> Resource: ...
    def children(self, folder_id: str, drive_id: str | None) -> list[Resource]: ...
    def find_by_markers(self, parent_id: str, operation_id: str, action_id: str) -> list[Resource]: ...
    def create_folder(self, name: str, parent_id: str, operation_id: str, action_id: str) -> Resource: ...
    def create_document(self, name: str, parent_id: str, operation_id: str, action_id: str) -> Resource: ...
    def move(self, file_id: str, add_parent: str, remove_parents: tuple[str, ...]) -> Resource: ...
    def copy(self, file_id: str, name: str, parent_id: str, operation_id: str, action_id: str) -> Resource: ...
    def download(self, file_id: str, destination: Path) -> None: ...
    def upload(self, name: str, parent_id: str, source: Path, mime_type: str, operation_id: str,
               action_id: str) -> Resource: ...
    def upload_converted(self, name: str, parent_id: str, source: Path, source_mime_type: str, operation_id: str,
                         action_id: str) -> Resource: ...


_HTTP_ERRORS = {
    401: ("oauth_login_required", "La sesión de Google no es válida; ejecute `litman login`"),
    403: ("insufficient_permission", "La cuenta o la aplicación no tienen permiso para este recurso de Drive"),
    404: ("not_found", "El recurso no existe o la aplicación no tiene acceso a él con el scope OAuth actual"),
}


def http_error(status: int) -> HarnessError:
    """The stable harness error for a failed Drive HTTP status (shared by every Drive adapter)."""
    code, message = _HTTP_ERRORS.get(status, ("drive_error", "Drive rechazó la solicitud"))
    return HarnessError(code, message, details={"http_status": status})


def _execute(request: Any, *, chunk: bool = False) -> Any:
    """Run a Drive request and translate HTTP failures into stable harness errors."""
    from googleapiclient.errors import HttpError
    try:
        return request.next_chunk() if chunk else request.execute()
    except HttpError as exc:
        raise http_error(int(getattr(exc.resp, "status", 0) or 0)) from exc


def _markers(operation_id: str, action_id: str) -> dict[str, str]:
    return {OPERATION_MARKER: operation_id, ACTION_MARKER: action_id}


def _quoted(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


class GoogleDriveGateway:
    """Narrow personal-OAuth Drive adapter.  It never reads service-account files."""

    def __init__(self, service: Any):
        self.service = service

    def about(self) -> dict[str, Any]:
        # about.get does not accept supportsAllDrives.
        return _execute(self.service.about().get(fields="user(permissionId,emailAddress,displayName)"))

    def get(self, file_id: str) -> Resource:
        return Resource.from_api(_execute(self.service.files().get(fileId=file_id, fields=_FIELDS, **_OPTIONS)))

    def children(self, folder_id: str, drive_id: str | None) -> list[Resource]:
        return self._list(f"{_quoted(folder_id)} in parents and trashed = false", drive_id)

    def find_by_markers(self, parent_id: str, operation_id: str, action_id: str) -> list[Resource]:
        """Search only inside the given parent folder; never a global Drive search."""
        query = (f"{_quoted(parent_id)} in parents and trashed = false"
                 f" and appProperties has {{ key='{OPERATION_MARKER}' and value={_quoted(operation_id)} }}"
                 f" and appProperties has {{ key='{ACTION_MARKER}' and value={_quoted(action_id)} }}")
        parent = self.get(parent_id)
        return [item for item in self._list(query, parent.drive_id) if item.has_markers(operation_id, action_id)]

    def _list(self, query: str, drive_id: str | None) -> list[Resource]:
        request: dict[str, Any] = {
            "q": query, "spaces": "drive",
            "fields": f"nextPageToken,incompleteSearch,files({_FIELDS})",
            "pageSize": 1000, "includeItemsFromAllDrives": True, **_OPTIONS,
        }
        if drive_id:
            request.update(corpora="drive", driveId=drive_id)
        else:
            request["corpora"] = "user"
        result: list[Resource] = []
        token: str | None = None
        seen: set[str] = set()
        while True:
            page = _execute(self.service.files().list(**request, pageToken=token))
            if page.get("incompleteSearch"):
                raise HarnessError("drive_incomplete_search", "La búsqueda de Drive está incompleta")
            result.extend(Resource.from_api(item) for item in page.get("files", []))
            token = page.get("nextPageToken")
            if not token:
                return result
            if not isinstance(token, str) or token in seen:
                raise HarnessError("drive_invalid_page", "Paginación de Drive inválida")
            seen.add(token)

    def create_folder(self, name: str, parent_id: str, operation_id: str, action_id: str) -> Resource:
        body = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id],
                "appProperties": _markers(operation_id, action_id)}
        return Resource.from_api(_execute(self.service.files().create(body=body, fields=_FIELDS, **_OPTIONS)))

    def create_document(self, name: str, parent_id: str, operation_id: str, action_id: str) -> Resource:
        """Create an empty native Google Doc with the action markers."""
        body = {"name": name, "mimeType": GOOGLE_DOC_MIME, "parents": [parent_id],
                "appProperties": _markers(operation_id, action_id)}
        return Resource.from_api(_execute(self.service.files().create(body=body, fields=_FIELDS, **_OPTIONS)))

    def move(self, file_id: str, add_parent: str, remove_parents: tuple[str, ...]) -> Resource:
        """Change the parents of a file; it keeps its ID."""
        request = self.service.files().update(fileId=file_id, addParents=add_parent,
                                              removeParents=",".join(remove_parents), body={}, fields=_FIELDS,
                                              **_OPTIONS)
        return Resource.from_api(_execute(request))

    def copy(self, file_id: str, name: str, parent_id: str, operation_id: str, action_id: str) -> Resource:
        """Copy a file into ``parent_id`` with the action markers; the source is untouched."""
        body = {"name": name, "parents": [parent_id], "appProperties": _markers(operation_id, action_id)}
        return Resource.from_api(_execute(self.service.files().copy(fileId=file_id, body=body, fields=_FIELDS,
                                                                    **_OPTIONS)))

    def download(self, file_id: str, destination: Path) -> None:
        from googleapiclient.http import MediaIoBaseDownload
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with destination.open("wb") as output:
            downloader = MediaIoBaseDownload(output, self.service.files().get_media(fileId=file_id, **_OPTIONS))
            done = False
            while not done:
                _, done = _execute(downloader, chunk=True)

    def upload(self, name: str, parent_id: str, source: Path, mime_type: str, operation_id: str,
               action_id: str) -> Resource:
        return self._create_media({"name": name, "parents": [parent_id],
                                   "appProperties": _markers(operation_id, action_id)}, source, mime_type)

    def upload_converted(self, name: str, parent_id: str, source: Path, source_mime_type: str, operation_id: str,
                         action_id: str) -> Resource:
        """Upload a DOCX converting it to a native Google Doc directly in its destination."""
        return self._create_media({"name": name, "parents": [parent_id], "mimeType": GOOGLE_DOC_MIME,
                                   "appProperties": _markers(operation_id, action_id)}, source, source_mime_type)

    def _create_media(self, body: dict[str, Any], source: Path, mime_type: str) -> Resource:
        from googleapiclient.http import MediaFileUpload
        media = MediaFileUpload(str(source), mimetype=mime_type)
        raw = _execute(self.service.files().create(body=body, media_body=media, fields=_FIELDS, **_OPTIONS))
        return Resource.from_api(raw)
