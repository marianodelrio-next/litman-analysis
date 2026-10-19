"""Manifest v1 (``_LitMan/manifest.json``): the shared, recoverable dossier state."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from typing import Any
from uuid import uuid4

from ..errors import HarnessError
from .models import Resource

SCHEMA_VERSION = "litman-dossier-v1"
MANIFEST_NAME = "manifest.json"
CONTEXT_NAME = "contexto.md"
PHASES = ("sin_analisis", "analisis_inicial", "analisis_detallado", "oferta_en_preparacion", "entregada")
FOLDER_ROLES = (("originals", "Originales"), ("initial", "Analisis inicial"), ("detailed", "Analisis detallado"),
                ("offer", "Oferta"), ("internal", "Interno"), ("deliveries", "Entregas"), ("litman", "_LitMan"))
ROLE_NAMES = tuple(role for role, _ in FOLDER_ROLES)
OFFER_ORIGINS = ("existing_external", "core_conversion")
# Phase reached by publishing each analysis type; publishing only ever advances it.
PHASE_AFTER_ANALYSIS = {"assessment": "analisis_inicial", "detailed-analysis": "analisis_detallado"}


def advanced_phase(current: str, job_type: str) -> str | None:
    """Target phase if ``current`` is behind it; ``None`` otherwise (never goes back)."""
    target = PHASE_AFTER_ANALYSIS[job_type]
    return target if PHASES.index(current) < PHASES.index(target) else None
# Dossier summary: closed keys in a fixed order, stable for code agents.
SUMMARY_LABELS = {
    "objeto": "Objeto", "organismo": "Organismo", "expediente": "Expediente", "procedimiento": "Procedimiento",
    "presupuesto": "Presupuesto", "valor_estimado": "Valor estimado", "plazo_ejecucion": "Plazo de ejecución",
    "fecha_limite": "Fecha límite de presentación", "lotes": "Lotes", "solvencia_economica": "Solvencia económica",
    "solvencia_tecnica": "Solvencia técnica", "equipo": "Equipo",
    "criterios_adjudicacion": "Criterios de adjudicación",
    "recomendacion": "Recomendación", "alertas": "Alertas",
}
SUMMARY_KEYS = tuple(SUMMARY_LABELS)
SUMMARY_REQUIRED = ("objeto", "organismo", "presupuesto", "fecha_limite")
SUMMARY_VALUE_MAX = 300
NO_CONSTA = "No consta"
SUMMARY_ORIGIN = "assistant_proposal_accepted"


def _ids(items: list[Any], key: str) -> list[Any]:
    return [item.get(key) if isinstance(item, dict) else None for item in items]


@dataclass
class Manifest:
    dossier_id: str
    root_folder_id: str
    shared_drive_id: str | None
    workflow_phase: str = "sin_analisis"
    folders: dict[str, str | None] = field(default_factory=dict)
    context_file_id: str | None = None
    context_sha256: str | None = None
    originals: list[dict[str, Any]] = field(default_factory=list)
    analyses: list[dict[str, Any]] = field(default_factory=list)
    live_offer: dict[str, Any] | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] | None = None
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def new(cls, root: Resource, dossier_id: str | None = None) -> "Manifest":
        return cls(dossier_id or str(uuid4()), root.id, root.drive_id, folders={role: None for role in ROLE_NAMES})

    @classmethod
    def load(cls, data: Any) -> "Manifest":
        if not isinstance(data, dict):
            raise HarnessError("invalid_manifest", "manifest.json debe ser un objeto")
        if data.get("schema_version") != SCHEMA_VERSION:
            raise HarnessError("unsupported_manifest", "La versión del manifiesto no se puede reescribir",
                               details={"schema_version": data.get("schema_version")})
        required = ("dossier_id", "root_folder_id", "workflow_phase")
        if any(not isinstance(data.get(key), str) for key in required) or not isinstance(data.get("folders"), dict):
            raise HarnessError("invalid_manifest", "El manifiesto no cumple el contrato v1")
        try:
            manifest = cls(**{key: data[key] for key in cls.__dataclass_fields__ if key in data})
        except TypeError as exc:
            raise HarnessError("invalid_manifest", "El manifiesto no cumple el contrato v1") from exc
        manifest.validate()
        return manifest

    @classmethod
    def parse(cls, content: str) -> "Manifest":
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise HarnessError("invalid_manifest", "manifest.json no contiene JSON válido") from exc
        return cls.load(payload)

    def validate(self) -> None:
        if self.workflow_phase not in PHASES:
            raise HarnessError("invalid_manifest", "Fase del manifiesto desconocida")
        if not set(self.folders) <= set(ROLE_NAMES):
            raise HarnessError("invalid_manifest", "El manifiesto contiene funciones de carpeta desconocidas")
        for name in ("originals", "analyses", "history"):
            if not isinstance(getattr(self, name), list) or not all(isinstance(i, dict) for i in getattr(self, name)):
                raise HarnessError("invalid_manifest", f"El campo {name} debe ser una lista de objetos")
        for items, key, label in ((self.originals, "file_id", "originales"),
                                  (self.analyses, "operation_id", "análisis")):
            ids = _ids(items, key)
            if len(ids) != len(set(ids)) or any(not isinstance(item, str) or not item for item in ids):
                raise HarnessError("invalid_manifest", f"El manifiesto contiene {label} ausentes o duplicados")
        if self.summary is not None:
            self._validate_summary()
        folder_ids = [value for value in self.folders.values() if value]
        if len(folder_ids) != len(set(folder_ids)) or not all(isinstance(value, str) for value in folder_ids):
            raise HarnessError("invalid_manifest", "El manifiesto contiene carpetas duplicadas o inválidas")
        if self.live_offer is not None and (
                not isinstance(self.live_offer, dict) or not isinstance(self.live_offer.get("document_id"), str)
                or self.live_offer.get("origin_kind") not in OFFER_ORIGINS):
            raise HarnessError("invalid_manifest", "La oferta viva no contiene un document_id y origen válidos")
        for value in (self.context_file_id, self.context_sha256):
            if value is not None and not isinstance(value, str):
                raise HarnessError("invalid_manifest", "El contexto no contiene un ID válido")

    def _validate_summary(self) -> None:
        summary = self.summary
        items = summary.get("items") if isinstance(summary, dict) else None
        keys = [item.get("key") for item in items] if isinstance(items, list) and all(
            isinstance(item, dict) for item in items) else None
        if (keys is None or len(keys) != len(set(keys)) or not set(keys) <= set(SUMMARY_KEYS)
                or not all(isinstance(item.get("value"), str) for item in items)
                or not all(item.get("source_file_id") is None or isinstance(item["source_file_id"], str)
                           for item in items)
                or not isinstance(summary.get("based_on_analyses"), list)):
            raise HarnessError("invalid_manifest", "El resumen de la licitación no cumple el contrato v1")

    def summary_sources(self) -> dict[str, str]:
        """Registered documents a summary line may cite: file_id → kind (original or artifact).

        The source of a copied original stays citable: earlier summaries and analyses used its ID.
        """
        sources = {item["file_id"]: "original" for item in self.originals}
        sources.update({item["copied_from"]: "original" for item in self.originals
                        if isinstance(item.get("copied_from"), str)})
        for analysis in self.analyses:
            if analysis.get("status") == "published":
                for artifact in analysis.get("artifacts") or []:
                    if isinstance(artifact.get("file_id"), str):
                        sources[artifact["file_id"]] = "artifact"
        return sources

    def published_analyses(self) -> list[str]:
        return [item["operation_id"] for item in self.analyses if item.get("status") == "published"]

    def json(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    def serialize(self) -> str:
        return json.dumps(self.json(), sort_keys=True, ensure_ascii=False, indent=2) + "\n"

    def references(self) -> list[tuple[str, Any]]:
        """Every Drive ID the manifest points to, by kind."""
        refs: list[tuple[str, Any]] = [("folder", value) for value in self.folders.values() if value]
        refs += [("original", item.get("file_id")) for item in self.originals]
        if self.context_file_id:
            refs.append(("context", self.context_file_id))
        if self.live_offer:
            refs.append(("live_offer", self.live_offer.get("document_id")))
        for analysis in self.analyses:
            if analysis.get("folder_id"):
                refs.append(("analysis_folder", analysis.get("folder_id")))
        return refs
