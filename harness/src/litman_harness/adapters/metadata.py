"""Deterministic read-only gateway used by development CLI/MCP configuration.

It intentionally stores metadata only, never OAuth material.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..dossier.models import Resource
from ..errors import HarnessError


class MetadataGateway:
    def __init__(self, path: Path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HarnessError("adapter_not_configured", "No hay configuración de metadatos legible") from exc
        self._about = data.get("about", {})
        self._resources = {item.id: item for item in (Resource.from_api(raw) for raw in data.get("resources", []))}

    def about(self):
        return self._about

    def get(self, file_id):
        try:
            return self._resources[file_id]
        except KeyError as exc:
            raise HarnessError("not_found", "No existe el recurso solicitado") from exc

    def children(self, folder_id, drive_id):
        return [item for item in self._resources.values() if folder_id in item.parents and not item.trashed]

    def find_by_markers(self, parent_id, operation_id, action_id):
        return [item for item in self.children(parent_id, None) if item.has_markers(operation_id, action_id)]

    def create_folder(self, *args):
        raise HarnessError("read_only_adapter", "El adaptador de metadatos no puede escribir")

    def create_document(self, *args):
        raise HarnessError("read_only_adapter", "El adaptador de metadatos no puede escribir")

    def move(self, *args):
        raise HarnessError("read_only_adapter", "El adaptador de metadatos no puede escribir")

    def copy(self, *args):
        raise HarnessError("read_only_adapter", "El adaptador de metadatos no puede escribir")

    def rename(self, *args):
        raise HarnessError("read_only_adapter", "El adaptador de metadatos no puede escribir")

    def trash(self, *args):
        raise HarnessError("read_only_adapter", "El adaptador de metadatos no puede escribir")

    def download(self, *args):
        raise HarnessError("read_only_adapter", "El adaptador de metadatos no puede descargar")

    def export(self, *args):
        raise HarnessError("read_only_adapter", "El adaptador de metadatos no puede descargar")

    def comments(self, *args):
        raise HarnessError("read_only_adapter", "El adaptador de metadatos no puede leer comentarios")

    def create_comment(self, *args):
        raise HarnessError("read_only_adapter", "El adaptador de metadatos no puede escribir")

    def create_reply(self, *args, **kwargs):
        raise HarnessError("read_only_adapter", "El adaptador de metadatos no puede escribir")

    def upload(self, *args):
        raise HarnessError("read_only_adapter", "El adaptador de metadatos no puede escribir")

    def upload_converted(self, *args):
        raise HarnessError("read_only_adapter", "El adaptador de metadatos no puede escribir")


class MetadataDocsGateway:
    """Docs counterpart of the metadata adapter: it holds no document content and never writes."""

    def get(self, *args):
        raise HarnessError("read_only_adapter", "El adaptador de metadatos no puede leer documentos de Google Docs")

    def batch_update(self, *args):
        raise HarnessError("read_only_adapter", "El adaptador de metadatos no puede escribir")


class MetadataSheetsGateway:
    """Sheets counterpart of the metadata adapter: it holds no spreadsheet content and never writes."""

    def get(self, *args):
        raise HarnessError("read_only_adapter", "El adaptador de metadatos no puede leer hojas de cálculo")

    def values(self, *args, **kwargs):
        raise HarnessError("read_only_adapter", "El adaptador de metadatos no puede leer hojas de cálculo")

    def update(self, *args, **kwargs):
        raise HarnessError("read_only_adapter", "El adaptador de metadatos no puede escribir")
