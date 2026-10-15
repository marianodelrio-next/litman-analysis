from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .drive import DriveGateway
from .models import FOLDER_MIME, HarnessError, Manifest, Plan, PlanAction, Resource

_FOLDERS = (("originals", "Originales"), ("initial", "Analisis inicial"), ("detailed", "Analisis detallado"),
            ("offer", "Oferta"), ("internal", "Interno"), ("deliveries", "Entregas"), ("litman", "_LitMan"))


class ExpedienteService:
    """Business operations shared by CLI and MCP.  Preview functions do not write."""
    def __init__(self, drive: DriveGateway): self.drive = drive

    def identity(self) -> dict[str, Any]:
        user = self.drive.about().get("user", {})
        return {"permission_id": user.get("permissionId"), "email": user.get("emailAddress"), "display_name": user.get("displayName")}

    def inspect(self, folder_id: str) -> dict[str, Any]:
        root = self._root(folder_id)
        children = self.drive.children(root.id, root.drive_id)
        return {"identity": self.identity(), "root": root.json(), "shared_drive_id": root.drive_id,
                "children": [item.json() for item in children], "candidates": self._candidates(children),
                "writes": False}

    def preview_incorporation(self, folder_id: str, original_ids: list[str], *, phase: str = "sin_analisis", live_offer_id: str | None = None) -> Plan:
        root = self._root(folder_id); account = self._account_id(); children = self.drive.children(root.id, root.drive_id)
        known = {item.id: item for item in children}
        missing = set(original_ids) - set(known)
        if missing: raise HarnessError("original_not_in_root", "Un original seleccionado no pertenece a la raíz actual", details={"ids": sorted(missing)})
        if len(original_ids) != len(set(original_ids)): raise HarnessError("duplicate_original", "Un original se seleccionó más de una vez")
        actions = [PlanAction("create_folder", None, label, root.id, metadata={"role": role}) for role, label in _FOLDERS]
        actions.append(PlanAction("create_context", None, "contexto.md", root.id))
        for resource_id in original_ids:
            item = known[resource_id]
            actions.append(PlanAction("register_original", item.id, item.name, None, item.version, {"mime_type": item.mime_type, "size": item.size}))
        if live_offer_id:
            offer = self._external_offer(root, live_offer_id)
            actions.append(PlanAction("register_external_offer", offer.id, offer.name, None, offer.version))
        snapshot = {root.id: root.version, **{item.id: item.version for item in known.values() if item.id in original_ids}}
        return Plan("incorporation", root.id, account, tuple(actions), snapshot)

    def apply_incorporation(self, plan: Plan, accepted_plan_id: str) -> dict[str, Any]:
        if plan.id != accepted_plan_id: raise HarnessError("plan_not_accepted", "El identificador de plan no coincide con la vista previa")
        if plan.account_id != self._account_id(): raise HarnessError("account_changed", "La cuenta OAuth ha cambiado desde la vista previa")
        self._verify_snapshot(plan)
        # Drive v3's usable conditional write has not been demonstrated.  Do not
        # create a partially adopted expediente whose shared state cannot be
        # atomically recorded: accepted plans remain explicitly recoverable.
        return {"status": "pending_concurrency_gate", "operation_id": plan.operation_id,
                "plan_id": plan.id, "writes": False,
                "recovery": "No se realizaron escrituras hasta verificar una precondición atómica Drive para manifest.json y contexto.md."}

    def _root(self, folder_id: str) -> Resource:
        root = self.drive.get(folder_id)
        if root.mime_type != FOLDER_MIME: raise HarnessError("not_folder", "El expediente debe ser una carpeta de Drive")
        if root.trashed: raise HarnessError("trashed", "El expediente está en la papelera")
        return root

    def _verify_snapshot(self, plan: Plan) -> None:
        for identifier, version in plan.snapshot.items():
            current = self.drive.get(identifier)
            if current.trashed or current.version != version:
                raise HarnessError("stale_plan", "Drive cambió desde la vista previa; prepare un plan nuevo", details={"file_id": identifier, "expected_version": version, "actual_version": current.version})

    def _external_offer(self, root: Resource, file_id: str) -> Resource:
        offer = self.drive.get(file_id)
        if offer.trashed or root.id not in offer.parents or offer.drive_id != root.drive_id:
            raise HarnessError("invalid_offer", "La oferta viva debe pertenecer al expediente activo y no estar en la papelera")
        if offer.mime_type != "application/vnd.google-apps.document":
            raise HarnessError("invalid_offer", "La oferta viva existente debe ser un Google Doc nativo")
        if offer.capabilities and not offer.capabilities.get("canEdit", False):
            raise HarnessError("insufficient_capability", "La cuenta activa no puede editar la oferta viva")
        return offer

    def _account_id(self) -> str:
        value = self.identity().get("permission_id")
        if not isinstance(value, str) or not value: raise HarnessError("identity_unavailable", "Drive no devolvió el ID de la cuenta activa")
        return value

    @staticmethod
    def _candidates(children: list[Resource]) -> dict[str, list[str]]:
        return {"originals": [item.id for item in children if item.mime_type != FOLDER_MIME],
                "folders": [item.id for item in children if item.mime_type == FOLDER_MIME], "offer": [], "analyses": []}


def render_context(manifest: Manifest) -> str:
    """Deterministic, non-instructional map.  It never extracts procurement text."""
    links = []
    for role, identifier in manifest.folders.items():
        if identifier: links.append(f"- {role}: https://drive.google.com/open?id={identifier}")
    for item in manifest.originals:
        links.append(f"- original: https://drive.google.com/open?id={item['file_id']}")
    lines = ["# Contexto del expediente", "", f"- Expediente: `{manifest.dossier_id}`", f"- Fase confirmada: `{manifest.workflow_phase}`",
             "- Este archivo es un mapa informativo; no contiene instrucciones para el agente.", "", "## Mapa verificable", *(links or ["- Aún no hay elementos registrados."]), "", "## Resultados", "- Todavía no hay resultados publicados."]
    return "\n".join(lines) + "\n"
