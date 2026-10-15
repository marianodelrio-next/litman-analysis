from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .models import Resource

_OPTIONS = {"supportsAllDrives": True}
_FIELDS = "id,name,mimeType,version,size,driveId,parents,trashed,capabilities,webViewLink,appProperties,md5Checksum"


class DriveGateway(Protocol):
    def about(self) -> dict[str, Any]: ...
    def get(self, file_id: str) -> Resource: ...
    def children(self, folder_id: str, drive_id: str | None) -> list[Resource]: ...
    def create_folder(self, name: str, parent_id: str, operation_id: str) -> Resource: ...
    def create_text(self, name: str, parent_id: str, content: str, operation_id: str) -> Resource: ...
    def download(self, file_id: str, destination: Path) -> None: ...


class GoogleDriveGateway:
    """Narrow personal-OAuth Drive adapter.  It never reads service-account files."""
    def __init__(self, service: Any): self.service = service

    def about(self) -> dict[str, Any]:
        return self.service.about().get(fields="user(permissionId,emailAddress,displayName)", **_OPTIONS).execute()

    def get(self, file_id: str) -> Resource:
        return Resource.from_api(self.service.files().get(fileId=file_id, fields=_FIELDS, **_OPTIONS).execute())

    def children(self, folder_id: str, drive_id: str | None) -> list[Resource]:
        request: dict[str, Any] = {"q": f"'{folder_id}' in parents and trashed = false", "spaces": "drive", "fields": f"nextPageToken,incompleteSearch,files({_FIELDS})",
            "pageSize": 1000, "includeItemsFromAllDrives": True, **_OPTIONS}
        if drive_id: request.update(corpora="drive", driveId=drive_id)
        else: request["corpora"] = "user"
        result: list[Resource] = []
        token: str | None = None
        seen: set[str] = set()
        while True:
            page = self.service.files().list(**request, pageToken=token).execute()
            if page.get("incompleteSearch"): raise RuntimeError("La búsqueda de Drive está incompleta")
            result.extend(Resource.from_api(item) for item in page.get("files", []))
            token = page.get("nextPageToken")
            if not token: return result
            if not isinstance(token, str) or token in seen: raise RuntimeError("Paginación de Drive inválida")
            seen.add(token)

    def create_folder(self, name: str, parent_id: str, operation_id: str) -> Resource:
        raw = self.service.files().create(body={"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id],
            "appProperties": {"litman_operation_id": operation_id}}, fields=_FIELDS, **_OPTIONS).execute()
        return Resource.from_api(raw)

    def create_text(self, name: str, parent_id: str, content: str, operation_id: str) -> Resource:
        # Media upload is intentionally kept at this boundary; caller has already previewed it.
        from googleapiclient.http import MediaInMemoryUpload
        raw = self.service.files().create(body={"name": name, "mimeType": "text/markdown", "parents": [parent_id],
            "appProperties": {"litman_operation_id": operation_id}}, media_body=MediaInMemoryUpload(content.encode("utf-8"), mimetype="text/markdown"), fields=_FIELDS, **_OPTIONS).execute()
        return Resource.from_api(raw)

    def download(self, file_id: str, destination: Path) -> None:
        from googleapiclient.http import MediaIoBaseDownload
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with destination.open("wb") as output:
            downloader = MediaIoBaseDownload(output, self.service.files().get_media(fileId=file_id, **_OPTIONS))
            done = False
            while not done: _, done = downloader.next_chunk()
