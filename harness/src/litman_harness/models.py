from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any
from uuid import uuid4

SCHEMA_VERSION = "litman-dossier-v1"
FOLDER_MIME = "application/vnd.google-apps.folder"


class HarnessError(ValueError):
    """Stable, JSON-safe harness failure with a machine readable code."""

    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code, self.details = code, details or {}


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
        return cls(identifier, str(raw.get("name") or ""), str(raw.get("mimeType") or "application/octet-stream"),
                   str(raw["version"]) if raw.get("version") is not None else None, parsed_size,
                   raw.get("driveId") if isinstance(raw.get("driveId"), str) else None,
                   tuple(item for item in raw.get("parents", []) if isinstance(item, str)), bool(raw.get("trashed")),
                   {str(k): bool(v) for k, v in caps.items()}, raw.get("webViewLink") if isinstance(raw.get("webViewLink"), str) else None)

    def json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PlanAction:
    kind: str
    resource_id: str | None
    name: str
    parent_id: str | None
    expected_version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Plan:
    kind: str
    root_folder_id: str
    account_id: str
    actions: tuple[PlanAction, ...]
    snapshot: dict[str, str | None]
    operation_id: str = field(default_factory=lambda: str(uuid4()))

    @property
    def id(self) -> str:
        data = {"kind": self.kind, "root": self.root_folder_id, "account": self.account_id,
                "actions": [action.json() for action in self.actions], "snapshot": self.snapshot,
                "operation": self.operation_id}
        return sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

    def json(self) -> dict[str, Any]:
        return {"plan_id": self.id, "operation_id": self.operation_id, "kind": self.kind,
                "root_folder_id": self.root_folder_id, "actions": [item.json() for item in self.actions],
                "snapshot": self.snapshot}


@dataclass
class Manifest:
    dossier_id: str
    root_folder_id: str
    shared_drive_id: str | None
    workflow_phase: str = "sin_analisis"
    folders: dict[str, str | None] = field(default_factory=dict)
    context_file_id: str | None = None
    originals: list[dict[str, Any]] = field(default_factory=list)
    analyses: list[dict[str, Any]] = field(default_factory=list)
    live_offer: dict[str, Any] | None = None
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def new(cls, root: Resource, dossier_id: str | None = None) -> "Manifest":
        return cls(dossier_id or str(uuid4()), root.id, root.drive_id, folders={"originals": None, "initial": None,
            "detailed": None, "offer": None, "internal": None, "deliveries": None, "litman": None})

    @classmethod
    def load(cls, data: dict[str, Any]) -> "Manifest":
        if data.get("schema_version") != SCHEMA_VERSION:
            raise HarnessError("unsupported_manifest", "La versión del manifiesto no se puede reescribir", details={"schema_version": data.get("schema_version")})
        required = ("dossier_id", "root_folder_id", "workflow_phase", "folders")
        if any(not isinstance(data.get(key), str) and key != "folders" for key in required) or not isinstance(data.get("folders"), dict):
            raise HarnessError("invalid_manifest", "El manifiesto no cumple el contrato v1")
        manifest = cls(**{key: data.get(key) for key in cls.__dataclass_fields__ if key in data})
        manifest.validate()
        return manifest

    def validate(self) -> None:
        ids = [item.get("file_id") for item in self.originals if isinstance(item, dict)]
        if len(ids) != len(set(ids)) or any(not isinstance(item, str) or not item for item in ids):
            raise HarnessError("invalid_manifest", "El manifiesto contiene originales ausentes o duplicados")
        folder_ids = [value for value in self.folders.values() if value]
        if len(folder_ids) != len(set(folder_ids)):
            raise HarnessError("invalid_manifest", "El manifiesto contiene carpetas duplicadas")

    def json(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)
