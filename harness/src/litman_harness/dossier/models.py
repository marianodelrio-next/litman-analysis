"""Drive resource value type used by the dossier and its adapters."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..errors import HarnessError

FOLDER_MIME = "application/vnd.google-apps.folder"
GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
NATIVE_PREFIX = "application/vnd.google-apps."
OPERATION_MARKER = "litman_operation_id"
ACTION_MARKER = "litman_action_id"


@dataclass(frozen=True)
class Resource:
    id: str
    name: str
    mime_type: str
    version: str | None = None
    size: int | None = None
    drive_id: str | None = None
    parents: tuple[str, ...] = ()
    trashed: bool = False
    capabilities: dict[str, bool] = field(default_factory=dict)
    web_view_link: str | None = None
    app_properties: dict[str, str] = field(default_factory=dict)
    # Content checksum: the only reliable change signal for binary originals.
    # Drive ``version`` also moves without content changes (opening a folder,
    # post-upload processing), so it is informative only.
    md5_checksum: str | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "Resource":
        identifier = raw.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise HarnessError("invalid_resource", "Drive devolvió un recurso sin ID válido")
        size = raw.get("size")
        try:
            parsed_size = int(size) if size is not None else None
        except (TypeError, ValueError) as exc:
            raise HarnessError("invalid_resource", f"Tamaño inválido para {identifier}") from exc
        caps = raw.get("capabilities") if isinstance(raw.get("capabilities"), dict) else {}
        drive_id = raw.get("driveId")
        link = raw.get("webViewLink")
        props = raw.get("appProperties") if isinstance(raw.get("appProperties"), dict) else {}
        return cls(
            identifier,
            str(raw.get("name") or ""),
            str(raw.get("mimeType") or "application/octet-stream"),
            str(raw["version"]) if raw.get("version") is not None else None,
            parsed_size,
            drive_id if isinstance(drive_id, str) else None,
            tuple(item for item in raw.get("parents", []) if isinstance(item, str)),
            bool(raw.get("trashed")),
            {str(key): bool(value) for key, value in caps.items()},
            link if isinstance(link, str) else None,
            {str(key): str(value) for key, value in props.items()},
            raw.get("md5Checksum") if isinstance(raw.get("md5Checksum"), str) else None,
        )

    def has_markers(self, operation_id: str, action_id: str) -> bool:
        return (self.app_properties.get(OPERATION_MARKER) == operation_id
                and self.app_properties.get(ACTION_MARKER) == action_id)

    def json(self) -> dict[str, Any]:
        return asdict(self)
