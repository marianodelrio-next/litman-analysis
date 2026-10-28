"""Dossier business operations shared by every transport.  Previews never write."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import tempfile
from typing import Any, Callable

from ..adapters.drive import DriveGateway
from ..analysis.inputs import ALLOWED_MIME_TYPES, require_checksum
from ..errors import HarnessError, safe_exception_message
from ..plans import PlanStore
from ..plans.models import OperationRecord, OperationStatus, Plan, PlanAction
from .context import context_sha256, render_context
from .manifest import CONTEXT_NAME, FOLDER_ROLES, MANIFEST_NAME, PHASES, ROLE_NAMES, Manifest
from .membership import belongs_to_root
from .models import FOLDER_MIME, GOOGLE_DOC_MIME, NATIVE_PREFIX, Resource
from .recommendation import recommend
from .shared_state import SharedStateCapability, UnavailableSharedState
from .tree import LITMAN_FOLDER, TreeItem, suggested_folder_ids, walk_tree

_FOLDER_LABELS = dict(FOLDER_ROLES)
_ORIGINALS = _FOLDER_LABELS["originals"]


def placement_strategy(item: Resource) -> str:
    """How an original reaches the ``originals`` folder; a missing capability counts as ``False``."""
    if item.capabilities.get("canMoveItemWithinDrive", False):
        return "move"
    return "copy" if item.capabilities.get("canCopy", False) else "in_place"


def placement_warning(strategy: str, name: str) -> str | None:
    if strategy == "copy":
        return (f"Sólo se puede copiar «{name}»: la copia queda en {_ORIGINALS} y el archivo de origen sigue "
                "donde estaba.")
    if strategy == "in_place":
        return (f"No hay permiso para mover ni copiar «{name}»: queda registrado donde está, fuera de "
                f"{_ORIGINALS}.")
    if strategy == "skipped":
        return (f"«{name}» cambió desde que se registró: no se coloca en {_ORIGINALS} hasta que una persona "
                "lo revise.")
    return None


def action_id(plan: Plan, action: PlanAction) -> str:
    key = f"{plan.operation_id}:{action.kind}:{action.resource_id}:{action.parent_id}:{action.name}"
    return sha256(key.encode()).hexdigest()[:24]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def summary_suggestions(manifest: Manifest) -> list[dict[str, str]]:
    """Suggest proposing (or refreshing) the dossier summary once results are published."""
    published = manifest.published_analyses()
    if not published:
        return []
    if not manifest.summary:
        return [{"kind": "propose_summary",
                 "reason": "Hay resultados publicados y la licitación aún no tiene resumen; el asistente puede "
                           "proponerlo para que la persona lo acepte."}]
    if set(published) - set(manifest.summary.get("based_on_analyses") or []):
        return [{"kind": "refresh_summary",
                 "reason": "Hay análisis publicados después del resumen; conviene revisarlo."}]
    return []


class OperationConflict(HarnessError):
    """Stops an operation without further writes; recorded as ``conflict``."""

    def __init__(self, message: str, *, details: dict[str, Any]):
        super().__init__("conflict", message, details=details)


@dataclass
class DossierState:
    root: Resource
    children: list[Resource]
    state: str = "unadopted"
    litman: Resource | None = None
    manifest_file: Resource | None = None
    manifest: Manifest | None = None
    manifest_sha256: str | None = None
    problem: dict[str, Any] | None = None
    missing: list[dict[str, str]] = field(default_factory=list)


class OperationRun:
    """Local progress of one accepted plan: completed actions, outputs and final status."""

    def __init__(self, store: PlanStore, account: str, plan: Plan, record: OperationRecord | None):
        self.store, self.account, self.plan = store, account, plan
        self.completed = list(record.completed_actions) if record else []
        self.outputs: dict[str, Any] = dict(record.outputs) if record else {}
        self.resources = tuple({"action_id": action_id(plan, action), "action": action.kind, "name": action.name,
                                "parent_id": action.parent_id, "resource_id": action.resource_id,
                                "operation_id": plan.operation_id} for action in plan.actions)

    def done(self, action: PlanAction) -> bool:
        return action_id(self.plan, action) in self.completed

    def output(self, action: PlanAction) -> dict[str, Any]:
        return self.outputs.get(action_id(self.plan, action), {})

    def complete(self, action: PlanAction, output: dict[str, Any] | None = None) -> None:
        identifier = action_id(self.plan, action)
        self.outputs[identifier] = output or {}
        if identifier not in self.completed:
            self.completed.append(identifier)
        self.save(OperationStatus.RUNNING)

    def note(self, action: PlanAction, output: dict[str, Any]) -> None:
        """Persist an intermediate decision without marking the action completed."""
        self.outputs[action_id(self.plan, action)] = output
        self.save(OperationStatus.RUNNING)

    def forget(self, action: PlanAction) -> None:
        self.outputs.pop(action_id(self.plan, action), None)
        self.save(OperationStatus.RUNNING)

    def save(self, status: OperationStatus, *, result: dict[str, Any] | None = None,
             conflict: dict[str, Any] | None = None) -> OperationRecord:
        record = OperationRecord(self.plan.operation_id, self.plan.id, self.plan.kind, status,
                                 tuple(self.completed), self.resources, self.outputs, result, conflict)
        self.store.save_operation(self.account, self.plan.operation_id, record)
        return record

    def envelope(self, status: str, **extra: Any) -> dict[str, Any]:
        return {"status": status, "operation_id": self.plan.operation_id, "plan_id": self.plan.id,
                "kind": self.plan.kind, "completed_actions": list(self.completed), **extra}


class ExpedienteService:
    """Business operations shared by CLI and MCP.  Preview functions do not write."""

    def __init__(self, drive: DriveGateway, plan_store: PlanStore | None = None,
                 shared_state: SharedStateCapability | None = None):
        self.drive = drive
        self.plan_store = plan_store
        self.shared_state = shared_state or UnavailableSharedState()

    # -- queries -------------------------------------------------------------------------------

    def identity(self) -> dict[str, Any]:
        user = self.drive.about().get("user", {})
        return {"permission_id": user.get("permissionId"), "email": user.get("emailAddress"),
                "display_name": user.get("displayName")}

    def inspect(self, folder_id: str) -> dict[str, Any]:
        root = self.root(folder_id)
        children = self.drive.children(root.id, root.drive_id)
        return self._inspection(root, children, None)

    def _inspection(self, root: Resource, children: list[Resource], manifest: Manifest | None,
                    inventory: tuple[list[TreeItem], bool] | None = None) -> dict[str, Any]:
        tree, truncated = inventory if inventory is not None else walk_tree(self.drive, root, children)
        candidates = self._candidates(tree, manifest)
        next_actions = self._next_actions(candidates)
        if any(item.name == "_LitMan" and item.mime_type == FOLDER_MIME for item in children):
            next_actions.append({"kind": "open_status",
                                 "reason": "Existe estado LitMan; consulte status para validar sus IDs."})
        return {"identity": self.identity(), "root": root.json(), "shared_drive_id": root.drive_id,
                "children": [item.json() for item in children], "tree": [item.json() for item in tree],
                "tree_truncated": truncated, "candidates": candidates, "next_actions": next_actions,
                "writes": False}

    def status(self, folder_id: str) -> dict[str, Any]:
        """Inspection plus the manifest below the connected root; never searches Drive globally."""
        root = self.root(folder_id)
        state = self.load_state(root)
        manifest = state.manifest
        inventory = walk_tree(self.drive, root, state.children)
        result = self._inspection(root, state.children, manifest, inventory)
        pending = self._pending_analyses(root.id)
        result.update({"state": state.state, "manifest": manifest.json() if manifest else None,
                       "manifest_file_id": state.manifest_file.id if state.manifest_file else None,
                       "problem": state.problem, "missing_resources": state.missing,
                       "drift": self._drift(root, state, inventory, result["candidates"]),
                       "candidate_scan_complete": not inventory[1],
                       "pending_publications": pending,
                       "next_actions": self._status_actions(state, result["candidates"], result["next_actions"],
                                                            pending),
                       "recommended_action": recommend(
                           folder_id=root.id, state=state.state, manifest=manifest, candidates=result["candidates"],
                           pending=pending, misplaced_originals=self._misplaced_originals(root, manifest))})
        return result

    def _drift(self, root: Resource, state: DossierState, inventory: tuple[list[TreeItem], bool],
               candidates: dict[str, Any]) -> list[dict[str, Any]]:
        """Describe observed differences without changing shared state or inferring identities."""
        tree, truncated = inventory
        known = {entry.resource.id: entry for entry in tree}
        drift: list[dict[str, Any]] = []

        def add(code: str, identifier: str | None = None, **values: Any) -> None:
            drift.append({"code": code, "id": identifier, **values})

        for identifier in candidates["originals"]:
            add("unregistered_original", identifier, suggested_tool="preview_incorporation")
        if truncated:
            add("candidate_scan_incomplete", suggested_tool="status")
        manifest = state.manifest
        if manifest is None:
            return drift
        unavailable = {item["id"]: item["reason"] for item in state.missing}
        for missing in state.missing:
            add("resource_unavailable", missing["id"], kind=missing["kind"],
                current=missing["reason"], suggested_tool="status")

        def resource(identifier: str) -> Resource | None:
            if identifier in unavailable:
                return None
            if identifier in known:
                return known[identifier].resource
            try:
                item = self.drive.get(identifier)
                return item if belongs_to_root(self.drive, root, item) else None
            except KeyError:
                return None
            except HarnessError as exc:
                if exc.code not in ("not_found", "insufficient_permission"):
                    raise
                return None

        def inside(identifier: str, item: Resource, folder_id: str | None) -> bool:
            if not folder_id:
                return False
            if identifier in known:
                return folder_id in known[identifier].ancestors
            try:
                return belongs_to_root(self.drive, self.drive.get(folder_id), item)
            except KeyError:
                return False
            except HarnessError as exc:
                if exc.code not in ("not_found", "insufficient_permission"):
                    raise
                return False

        for original in manifest.active_originals():
            identifier = original["file_id"]
            item = resource(identifier)
            if item is None:
                continue
            if original.get("observed_name") is not None and original["observed_name"] != item.name:
                add("original_name_changed", identifier, old=original["observed_name"], current=item.name,
                    suggested_tool="status")
            if original.get("md5_checksum") != item.md5_checksum:
                add("original_content_changed", identifier, old=original.get("md5_checksum"),
                    current=item.md5_checksum, suggested_tool="status")
            folder = manifest.folders.get("originals")
            if folder and original.get("placement") != "in_place" and not inside(identifier, item, folder):
                add("original_misplaced", identifier, old=folder, current=list(item.parents), suggested_tool="status")
        for analysis in manifest.analyses:
            if analysis.get("status") != "published":
                continue
            for artifact in analysis.get("artifacts") or []:
                identifier = artifact.get("file_id")
                if not isinstance(identifier, str) or (item := resource(identifier)) is None:
                    continue
                if artifact.get("name") is not None and artifact["name"] != item.name:
                    add("artifact_name_changed", identifier, old=artifact["name"], current=item.name,
                        suggested_tool="status")
                folder = analysis.get("folder_id")
                if folder and not inside(identifier, item, folder):
                    add("artifact_misplaced", identifier, old=folder, current=list(item.parents), suggested_tool="status")
        sources = {item.get("source_file_id") for item in (manifest.summary or {}).get("items", [])}
        retired = set(manifest.summary_sources(historical=True)) - set(manifest.summary_sources())
        for identifier in sorted(source for source in sources if isinstance(source, str)):
            if identifier in retired:
                add("summary_source_retired", identifier, suggested_tool="preview_summary")
            if resource(identifier) is None:
                add("summary_source_unavailable", identifier, suggested_tool="status")
        if manifest.context_file_id and manifest.context_sha256 and resource(manifest.context_file_id):
            try:
                current = context_sha256(self._download_text(manifest.context_file_id, "invalid_context"))
                if current != manifest.context_sha256:
                    add("context_changed", manifest.context_file_id, old=manifest.context_sha256, current=current,
                        suggested_tool="status")
            except KeyError:
                add("resource_unavailable", manifest.context_file_id, kind="context", current="unreadable",
                    suggested_tool="status")
            except HarnessError as exc:
                if exc.code not in ("not_found", "insufficient_permission", "invalid_context"):
                    raise
                add("resource_unavailable", manifest.context_file_id, kind="context", current="unreadable",
                    suggested_tool="status")
        return sorted(drift, key=lambda entry: (entry["code"], entry["id"] or "", entry.get("kind", "")))

    def _misplaced_originals(self, root: Resource, manifest: Manifest | None) -> list[str]:
        """Registered originals the incorporation preview would place (content unchanged since registration)."""
        if manifest is None or not manifest.folders.get("originals"):
            return []
        try:
            folder = self._originals_folder(manifest, {})
        except HarnessError as exc:
            if exc.code not in ("not_found", "insufficient_permission"):
                raise
            return []
        return [item.id for original, item in self._placeable_originals(root, manifest, folder)
                if item.md5_checksum == original.get("md5_checksum")]

    def recommendation_after(self, root_id: str, manifest: Manifest | None) -> dict[str, Any] | None:
        """Next step after a write, from the resulting manifest and local records (no Drive calls)."""
        if manifest is None:
            return None
        return recommend(folder_id=root_id, state="adopted", manifest=manifest,
                         pending=self._pending_analyses(root_id))

    def load_state(self, root: Resource) -> DossierState:
        """Locate and validate ``_LitMan/manifest.json`` below the connected root only."""
        children = self.drive.children(root.id, root.drive_id)
        state = DossierState(root, children)
        litman = [item for item in children if item.name == "_LitMan" and item.mime_type == FOLDER_MIME]
        if not litman:
            return state
        state.state = "partial"
        if len(litman) > 1:
            state.problem = {"code": "ambiguous_manifest_folder",
                             "message": "Hay más de una carpeta _LitMan; requiere reparación humana."}
            return state
        state.litman = litman[0]
        manifests = [item for item in self.drive.children(litman[0].id, root.drive_id) if item.name == MANIFEST_NAME]
        if len(manifests) != 1:
            state.problem = {"code": "manifest_missing" if not manifests else "manifest_duplicated",
                             "message": "Falta o está duplicado manifest.json."}
            return state
        state.manifest_file = manifests[0]
        try:
            text = self._download_text(manifests[0].id)
            state.manifest_sha256 = sha256(text.encode("utf-8")).hexdigest()
            manifest = Manifest.parse(text)
        except HarnessError as exc:
            state.state = "unsupported_manifest" if exc.code == "unsupported_manifest" else "partial"
            state.problem = {"code": exc.code, "message": str(exc), "details": exc.details}
            return state
        if manifest.root_folder_id != root.id or manifest.shared_drive_id != root.drive_id:
            state.problem = {"code": "invalid_manifest", "message": "El manifiesto no pertenece a esta licitación."}
            return state
        state.manifest = manifest
        state.missing = self._validate_references(root, manifest)
        state.state = "degraded" if state.missing else "adopted"
        return state

    def _download_text(self, file_id: str, error_code: str = "invalid_manifest") -> str:
        with tempfile.TemporaryDirectory(prefix="litman-state-") as directory:
            path = Path(directory) / "state"
            self.drive.download(file_id, path)
            try:
                return path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise HarnessError(error_code, "El archivo de estado no es legible") from exc

    def _validate_references(self, root: Resource, manifest: Manifest) -> list[dict[str, str]]:
        missing = []
        for kind, identifier in manifest.references():
            if not isinstance(identifier, str):
                missing.append({"kind": kind, "id": str(identifier), "reason": "invalid_id"})
                continue
            try:
                item = self.drive.get(identifier)
            except KeyError:
                missing.append({"kind": kind, "id": identifier, "reason": "not_found_or_revoked"})
                continue
            except HarnessError as exc:
                if exc.code not in ("not_found", "insufficient_permission"):
                    raise
                missing.append({"kind": kind, "id": identifier, "reason": "not_found_or_revoked"})
                continue
            if not belongs_to_root(self.drive, root, item):
                missing.append({"kind": kind, "id": identifier, "reason": "outside_tree_or_trashed"})
        return missing

    def _pending_analyses(self, root_id: str) -> list[dict[str, Any]]:
        if not self.plan_store:
            return []
        try:
            account = self.account_id()
        except HarnessError:
            return []
        return [{"operation_id": record.operation_id, "job_type": record.result.get("job_type"),
                 "publication_id": record.result.get("publication_id"),
                 "publication_plan_id": record.result.get("publication_plan_id")}
                for record in self.plan_store.records(account)
                if record.kind == "analysis" and record.status == OperationStatus.SUCCEEDED
                and record.result and record.result.get("root_folder_id") == root_id]

    # -- incorporation ---------------------------------------------------------------------------

    def preview_incorporation(self, folder_id: str, original_ids: list[str] | None = None, *,
                              phase: str | None = None, live_offer_id: str | None = None,
                              folder_ids: dict[str, str] | None = None, overwrite_context: bool = False) -> Plan:
        """Plan only what is missing inside the connected folder; nothing is written.

        ``overwrite_context`` is the explicit way out of a ``context_conflict``: it
        replaces ``contexto.md`` only if it still has the content seen now.
        """
        original_ids = list(original_ids or [])
        folder_ids = dict(folder_ids or {})
        root = self.root(folder_id)
        account = self.account_id()
        state = self.load_state(root)
        manifest = self.writable_manifest(state)
        if len(original_ids) != len(set(original_ids)):
            raise HarnessError("duplicate_original", "Un original se seleccionó más de una vez")
        if phase is not None and phase not in PHASES:
            raise HarnessError("invalid_phase", "Fase no admitida", details={"allowed": list(PHASES)})
        # Snapshot = content (MD5) of each new original.  Root, folders and offer are
        # rechecked by existence, trash and membership: Drive ``version`` moves
        # without content changes and is never a staleness signal.
        snapshot: dict[str, str | None] = {}
        actions: list[PlanAction] = []
        current_phase = manifest.workflow_phase if manifest else None
        target_phase = phase or (current_phase or "sin_analisis")
        if target_phase != current_phase:
            actions.append(PlanAction("set_phase", None, target_phase, None, metadata={"previous": current_phase}))
        actions += self._folder_actions(root, manifest, folder_ids)
        registered = ({value for item in manifest.originals for value in (item["file_id"], item.get("copied_from"))
                       if value} if manifest else set())
        originals_folder = self._originals_folder(manifest, folder_ids)
        placements = self._registered_placements(root, manifest, originals_folder)
        for identifier in original_ids:
            if identifier in registered:
                continue
            item = self.drive.get(identifier)
            if not belongs_to_root(self.drive, root, item):
                raise HarnessError("original_not_in_expediente",
                                   "Un original seleccionado no pertenece al expediente actual",
                                   details={"id": identifier})
            if item.mime_type == FOLDER_MIME or item.mime_type.startswith(NATIVE_PREFIX):
                raise HarnessError("invalid_original", "Un original debe ser un archivo no nativo de Google",
                                   details={"id": identifier})
            md5 = require_checksum(item)
            snapshot[item.id] = md5
            actions.append(PlanAction("register_original", item.id, item.name, None, md5,
                                      {"mime_type": item.mime_type, "size": item.size,
                                       "drive_version": item.version}))
            if not self._inside(originals_folder, item):
                placements.append(self._placement(item, md5, registered=False))
        actions += placements
        if live_offer_id:
            current_offer = manifest.live_offer["document_id"] if manifest and manifest.live_offer else None
            if current_offer and current_offer != live_offer_id:
                raise HarnessError("live_offer_exists", "Ya hay otra oferta viva registrada; no se sustituye",
                                   details={"document_id": current_offer})
            if not current_offer:
                offer = self._external_offer(root, live_offer_id)
                actions.append(PlanAction("register_external_offer", offer.id, offer.name, None))
        if overwrite_context and (manifest is None or not manifest.context_file_id):
            raise HarnessError("context_not_registered", "No hay contexto.md registrado que sobrescribir")
        if manifest is not None and not overwrite_context and all(
                action.kind == "place_original" and action.metadata["strategy"] == "skipped" for action in actions):
            raise HarnessError("no_changes", "El expediente ya contiene todo lo solicitado",
                               details={"placement_warnings": [action.metadata["warning"] for action in actions]})
        if manifest is None:
            actions.append(PlanAction("create_context", None, CONTEXT_NAME, root.id))
            actions.append(PlanAction("create_manifest", None, MANIFEST_NAME, None, metadata={"role": "litman"}))
        else:
            if overwrite_context:
                current = context_sha256(self._download_text(manifest.context_file_id, "invalid_context"))
                actions.append(PlanAction("replace_context", manifest.context_file_id, CONTEXT_NAME, root.id,
                                          metadata={"current_sha256": current,
                                                    "effect": "sobrescribe ediciones externas"}))
            else:
                actions.append(PlanAction("update_context", manifest.context_file_id, CONTEXT_NAME, root.id))
            # Staleness of shared state is judged by content, never by mixing Drive
            # v3 ``version`` with the v2 ETag that ``SharedStateCapability.read`` returns.
            actions.append(PlanAction("update_manifest", state.manifest_file.id, MANIFEST_NAME, None,
                                      metadata={"manifest_sha256": state.manifest_sha256}))
        plan = Plan("incorporation", root.id, account, tuple(actions), snapshot)
        self.store().save(plan)
        return plan

    def writable_manifest(self, state: DossierState) -> Manifest | None:
        if state.state == "unsupported_manifest":
            raise HarnessError("unsupported_manifest", "El manifiesto tiene una versión desconocida; sólo lectura")
        if state.problem is not None:
            raise HarnessError(state.problem["code"], "El estado LitMan requiere revisión humana antes de modificarlo",
                               details={"problem": state.problem})
        return state.manifest

    def _folder_actions(self, root: Resource, manifest: Manifest | None,
                        folder_ids: dict[str, str]) -> list[PlanAction]:
        unknown = sorted(set(folder_ids) - set(ROLE_NAMES))
        if unknown:
            raise HarnessError("invalid_folder_role", "Función de carpeta desconocida",
                               details={"unknown": unknown, "allowed": list(ROLE_NAMES)})
        if len(set(folder_ids.values())) != len(folder_ids):
            raise HarnessError("duplicate_folder", "Una carpeta se asignó a más de una función")
        actions = []
        for role in ROLE_NAMES:
            current = manifest.folders.get(role) if manifest else None
            requested = folder_ids.get(role)
            if current:
                if requested and requested != current:
                    raise HarnessError("folder_role_registered", "Esa función ya tiene otra carpeta registrada",
                                       details={"role": role, "folder_id": current})
                continue
            if requested:
                folder = self.drive.get(requested)
                if folder.mime_type != FOLDER_MIME or not belongs_to_root(self.drive, root, folder):
                    raise HarnessError("invalid_folder", "La carpeta indicada no es una carpeta de esta licitación",
                                       details={"role": role, "id": requested})
                actions.append(PlanAction("register_folder", folder.id, folder.name, None, metadata={"role": role}))
            else:
                actions.append(PlanAction("create_folder", None, _FOLDER_LABELS[role], root.id,
                                          metadata={"role": role}))
        return actions

    def _originals_folder(self, manifest: Manifest | None, folder_ids: dict[str, str]) -> Resource | None:
        """The ``originals`` folder already registered or being registered; ``None`` if the plan creates it."""
        folder_id = (manifest.folders.get("originals") if manifest else None) or folder_ids.get("originals")
        return self.drive.get(folder_id) if folder_id else None

    def _inside(self, folder: Resource | None, item: Resource) -> bool:
        return folder is not None and belongs_to_root(self.drive, folder, item)

    @staticmethod
    def _placement(item: Resource, md5: str | None, *, registered: bool, strategy: str | None = None) -> PlanAction:
        strategy = strategy or placement_strategy(item)
        return PlanAction("place_original", item.id, item.name, None, md5, {
            "strategy": strategy, "can_copy": item.capabilities.get("canCopy", False), "role": "originals",
            "registered": registered, "warning": placement_warning(strategy, item.name)})

    def _placeable_originals(self, root: Resource, manifest: Manifest | None,
                             originals_folder: Resource | None) -> list[tuple[dict[str, Any], Resource]]:
        """Registered originals in the dossier but outside ``originals``; never one kept ``in_place``.

        Unreachable, trashed or moved-out originals are left to status (``missing_resources``).
        Both the preview and the ``organize_originals`` recommendation use this one rule.
        """
        if manifest is None:
            return []
        placeable = []
        for original in manifest.active_originals():
            if original.get("placement") == "in_place":
                continue
            try:
                item = self.drive.get(original["file_id"])
            except HarnessError as exc:
                if exc.code not in ("not_found", "insufficient_permission"):
                    raise
                continue
            if belongs_to_root(self.drive, root, item) and not self._inside(originals_folder, item):
                placeable.append((original, item))
        return placeable

    def _registered_placements(self, root: Resource, manifest: Manifest | None,
                               originals_folder: Resource | None) -> list[PlanAction]:
        """An original whose content no longer matches the manifest is not placed (``skipped``, only a warning)."""
        actions = []
        for original, item in self._placeable_originals(root, manifest, originals_folder):
            expected = original.get("md5_checksum")
            strategy = None if item.md5_checksum == expected else "skipped"
            actions.append(self._placement(item, expected, registered=True, strategy=strategy))
        return actions

    def apply_incorporation(self, accepted_plan_id: str) -> dict[str, Any]:
        """Apply only a prior locally stored preview, never a client-supplied plan."""
        result = self.apply_plan(accepted_plan_id, "incorporation", self._run_incorporation)
        return self.with_recommendation(result)

    def with_recommendation(self, result: dict[str, Any]) -> dict[str, Any]:
        """Attach the next guided step computed on the manifest the operation produced."""
        manifest = result.get("manifest")
        if result.get("status") == "succeeded" and isinstance(manifest, dict):
            parsed = Manifest.load(manifest)
            result = {**result, "recommended_action": self.recommendation_after(parsed.root_folder_id, parsed)}
        return result

    def apply_plan(self, accepted_plan_id: str, kind: str,
                   runner: Callable[[OperationRun, Resource], dict[str, Any]]) -> dict[str, Any]:
        """Shared accept/gate/resume/conflict handling for every shared-state mutation."""
        store = self.store()
        account = self.account_id()
        # PlanStore.load binds the plan to this ID and the active account.
        plan = store.load(account, accepted_plan_id)
        if plan.kind != kind:
            raise HarnessError("invalid_plan", f"El plan aceptado no es de tipo {kind}")
        record = store.record(account, plan.operation_id)
        if record is not None and record.status in (OperationStatus.SUCCEEDED, OperationStatus.CONFLICT):
            return {**(record.result or {}), "replayed": True, "writes": False}
        run = OperationRun(store, account, plan, record)
        self._verify_snapshot(plan)
        if not getattr(self.shared_state, "available", False):
            run.save(OperationStatus.PLANNED)
            return run.envelope("pending_concurrency_gate", writes=False, operation={
                "resources": list(run.resources), "completed_actions": list(run.completed)},
                recovery="El adaptador configurado no permite escribir el estado compartido (p. ej. metadatos).")
        root = self.root(plan.root_folder_id)
        try:
            result = runner(run, root)
        except OperationConflict as exc:
            result = run.envelope("conflict", writes=bool(run.completed),
                                  conflict={"message": str(exc), **exc.details})
            run.save(OperationStatus.CONFLICT, result=result, conflict=result["conflict"])
            return result
        except HarnessError as exc:
            if exc.code == "concurrent_change":
                result = run.envelope("conflict", writes=bool(run.completed),
                                  conflict={"message": str(exc), **exc.details})
                run.save(OperationStatus.CONFLICT, result=result, conflict=result["conflict"])
                return result
            run.save(OperationStatus.RECOVERABLE)
            exc.details.setdefault("operation_id", plan.operation_id)
            raise
        except Exception as exc:
            run.save(OperationStatus.RECOVERABLE)
            raise HarnessError("operation_interrupted", "La operación quedó a medias; repita la aceptación para "
                               "reanudarla sin duplicar recursos",
                               details={"operation_id": plan.operation_id,
                                        "error": safe_exception_message(exc)}) from exc
        run.save(OperationStatus.SUCCEEDED, result=result)
        return result

    def _run_incorporation(self, run: OperationRun, root: Resource) -> dict[str, Any]:
        result = self._incorporate(run, root)
        warnings = [run.output(action).get("warning", action.metadata.get("warning"))
                    for action in run.plan.actions if action.kind == "place_original"]
        return {**result, "placement_warnings": [warning for warning in warnings if warning]}

    def _incorporate(self, run: OperationRun, root: Resource) -> dict[str, Any]:
        plan = run.plan
        resumed = self.resume_after_manifest(run)
        if resumed is not None:
            return resumed
        update = next((a for a in plan.actions if a.kind == "update_manifest"), None)
        if update is not None:
            base, manifest, manifest_version = self.read_manifest_unchanged(update)
        else:
            manifest_version = None
            base = None
            manifest = Manifest.new(root)
        account = self.performed_by()
        for action in plan.actions:
            if action.kind == "set_phase":
                manifest.workflow_phase = action.name
            elif action.kind == "register_folder":
                manifest.folders[action.metadata["role"]] = action.resource_id
            elif action.kind == "create_folder":
                if not run.done(action):
                    created = self.ensure_marked(run, action, action.parent_id, lambda a=action: (
                        self.drive.create_folder(a.name, a.parent_id, plan.operation_id, action_id(plan, a))))
                    if created.mime_type != FOLDER_MIME or not belongs_to_root(self.drive, root, created):
                        raise HarnessError("invalid_created_resource", "Drive creó un recurso fuera del expediente")
                    run.complete(action, {"resource_id": created.id})
                manifest.folders[action.metadata["role"]] = run.output(action)["resource_id"]
            elif action.kind == "register_original":
                manifest.originals.append({"file_id": action.resource_id, "observed_name": action.name,
                                           "mime_type": action.metadata.get("mime_type"),
                                           "size": action.metadata.get("size"),
                                           "drive_version": action.metadata.get("drive_version"),
                                           "md5_checksum": action.expected_version, "sha256": None,
                                           "provenance": "external"})
            elif action.kind == "place_original":
                if not run.done(action):
                    run.complete(action, self._place_original(run, action, manifest.folders.get("originals")))
                self._record_placement(manifest, action, run.output(action))
            elif action.kind == "register_external_offer":
                manifest.live_offer = {"document_id": action.resource_id, "origin_kind": "existing_external",
                                       "origin_analysis_id": None, "origin_artifact_id": None,
                                       "registered_by": account}
        manifest.history.append({"operation_id": plan.operation_id, "kind": plan.kind, "performed_by": account,
                                 "completed_at": now()})
        context_conflict = self.write_shared_state(run, root, manifest, base, manifest_version=manifest_version)
        return self.shared_result(run, manifest, context_conflict)

    def _place_original(self, run: OperationRun, action: PlanAction, folder_id: str | None) -> dict[str, Any]:
        """Move, copy or keep one original; a rejected move falls back to copy, then to ``in_place``."""
        strategy = action.metadata["strategy"]
        if strategy in ("in_place", "skipped"):
            return {"strategy": strategy, "resource_id": action.resource_id, "warning": action.metadata["warning"]}
        if not folder_id:
            raise HarnessError("invalid_plan", "El plan no registra la carpeta de originales")
        folder = self.drive.get(folder_id)
        if strategy == "move":
            item = self.drive.get(action.resource_id)
            if belongs_to_root(self.drive, folder, item):  # moved before an interruption
                return {"strategy": "move", "resource_id": item.id, "warning": None}
            try:
                moved = self.drive.move(item.id, folder.id, item.parents)
            except HarnessError as exc:
                if exc.code != "insufficient_permission":
                    raise
                strategy = "copy" if action.metadata.get("can_copy") else "in_place"
                if strategy == "in_place":
                    return {"strategy": strategy, "resource_id": action.resource_id,
                            "warning": placement_warning(strategy, action.name)}
            else:
                if not belongs_to_root(self.drive, folder, moved):
                    raise HarnessError("invalid_created_resource", "Drive no movió el original a su carpeta")
                return {"strategy": "move", "resource_id": moved.id, "warning": None}
        copied = self.ensure_marked(run, action, folder.id, lambda: self.drive.copy(
            action.resource_id, action.name, folder.id, run.plan.operation_id, action_id(run.plan, action)))
        if not belongs_to_root(self.drive, folder, copied) or copied.md5_checksum != action.expected_version:
            raise HarnessError("invalid_created_resource", "La copia del original no coincide con el original")
        return {"strategy": "copy", "resource_id": copied.id, "warning": placement_warning("copy", action.name)}

    @staticmethod
    def _record_placement(manifest: Manifest, action: PlanAction, outcome: dict[str, Any]) -> None:
        original = next(item for item in manifest.originals if item["file_id"] == action.resource_id)
        if outcome["strategy"] == "copy":
            original.update(file_id=outcome["resource_id"], copied_from=action.resource_id, provenance="copied")
        elif outcome["strategy"] == "in_place":
            original["placement"] = "in_place"
        else:
            original.pop("placement", None)

    def read_manifest_unchanged(self, update: PlanAction) -> tuple[Manifest, Manifest, str]:
        """Strict plans: the manifest must have the content seen in the preview.

        Returns the base manifest, a copy to modify and the ETag for the write.
        """
        content, version = self.shared_state.read(update.resource_id)
        if sha256(content.encode("utf-8")).hexdigest() != update.metadata.get("manifest_sha256"):
            raise OperationConflict("manifest.json cambió desde la vista previa",
                                    details={"action": "update_manifest"})
        return Manifest.parse(content), Manifest.parse(content), version

    def resume_after_manifest(self, run: OperationRun) -> dict[str, Any] | None:
        """If the manifest write already happened, finish the pending context write and report.

        An operation counts as finished only when both the manifest and the
        context action are done or resolved; a crash in between resumes here.
        """
        final = self._manifest_action(run.plan)
        if final is None:
            return None
        if not run.done(final) and final.kind == "update_manifest":
            # The write may have succeeded although its answer was lost: our history entry proves it.
            current = Manifest.parse(self.shared_state.read(final.resource_id)[0])
            if any(item.get("operation_id") == run.plan.operation_id for item in current.history):
                run.complete(final, {"resource_id": final.resource_id})
        if not run.done(final):
            return None
        context_conflict = self._finish_context(run)
        content, _ = self.shared_state.read(run.output(final)["resource_id"])
        return self.shared_result(run, Manifest.parse(content), context_conflict)

    def shared_result(self, run: OperationRun, manifest: Manifest,
                      context_conflict: dict[str, Any] | None, **extra: Any) -> dict[str, Any]:
        return run.envelope("succeeded", writes=True, manifest=manifest.json(),
                            context_file_id=manifest.context_file_id, context_conflict=context_conflict, **extra)

    def write_shared_state(self, run: OperationRun, root: Resource, manifest: Manifest, base: Manifest | None, *,
                           manifest_version: str | None = None) -> dict[str, Any] | None:
        """(a) check the context, (b) write the manifest, (c) write the context.

        A context edited outside LitMan never fails the operation: the manifest
        keeps the previous context SHA, nothing is overwritten and the result
        carries ``context_conflict``.  Returns that conflict, if any.
        """
        plan = run.plan
        manifest.upgrade()
        content = render_context(manifest, root.name)
        context_action = self._context_action(plan)
        if context_action.kind == "create_context":
            if not run.done(context_action):
                created = self.shared_state.create_if_absent(CONTEXT_NAME, root.id, content, plan.operation_id,
                                                             action_id(plan, context_action))
                run.complete(context_action, {"resource_id": created.id, "sha256": context_sha256(content)})
            manifest.context_file_id = run.output(context_action)["resource_id"]
            manifest.context_sha256 = run.output(context_action)["sha256"]
        else:
            decision = self._context_decision(run, context_action, base, content)
            manifest.context_file_id = base.context_file_id
            manifest.context_sha256 = (base.context_sha256 if decision["decision"] == "conflict"
                                       else decision["sha256"])
        manifest_action = self._manifest_action(plan)
        if manifest_action.kind == "create_manifest":
            litman = manifest.folders.get("litman")
            if not litman:
                raise HarnessError("invalid_plan", "El plan no registra la carpeta _LitMan")
            created = self.shared_state.create_if_absent(MANIFEST_NAME, litman, manifest.serialize(),
                                                         plan.operation_id, action_id(plan, manifest_action))
            run.complete(manifest_action, {"resource_id": created.id})
        else:
            if manifest_version is None:
                raise HarnessError("invalid_plan", "Falta la versión leída del manifiesto")
            try:
                self.shared_state.update_if_version(manifest_action.resource_id, manifest.serialize(),
                                                    manifest_version, plan.operation_id)
            except HarnessError as exc:
                if exc.code == "concurrent_change" and not run.done(context_action):
                    run.forget(context_action)  # the context must be re-derived from the next manifest
                raise
            run.complete(manifest_action, {"resource_id": manifest_action.resource_id})
        return self._finish_context(run)

    def _context_decision(self, run: OperationRun, action: PlanAction, base: Manifest | None,
                          content: str) -> dict[str, Any]:
        stored = run.output(action)
        if stored.get("decision") and stored.get("content") == content:
            return stored  # decided before an interruption, for this same content
        if base is None or not base.context_file_id:
            raise HarnessError("invalid_manifest", "El manifiesto no registra contexto.md")
        current, version = self.shared_state.read(base.context_file_id)
        current_sha = context_sha256(current)
        if action.kind == "replace_context":
            writable = current_sha == action.metadata.get("current_sha256")
            reason = "context_changed_since_preview"
        else:
            writable = current_sha == base.context_sha256
            reason = "edited_outside_litman"
        decision = {"file_id": base.context_file_id, "version": version, "content": content,
                    "sha256": context_sha256(content),
                    "decision": ("unchanged" if current == content else "write") if writable else "conflict",
                    "reason": None if writable else reason}
        run.note(action, decision)
        return decision

    def _finish_context(self, run: OperationRun) -> dict[str, Any] | None:
        """(c) Write the context with the version read in (a), or report why it was not written."""
        action = self._context_action(run.plan)
        if action.kind == "create_context":
            return None
        decision = run.output(action)
        if not run.done(action):
            if decision["decision"] == "write":
                try:
                    self.shared_state.update_if_version(decision["file_id"], decision["content"],
                                                        decision["version"], run.plan.operation_id)
                except HarnessError as exc:
                    if exc.code != "concurrent_change":
                        raise
                    decision = {**decision, "decision": "conflict", "reason": "concurrent_change"}
            run.complete(action, decision)
        if decision["decision"] != "conflict":
            return None
        return {"file_id": decision["file_id"], "proposed_content": decision["content"], "reason": decision["reason"]}

    @staticmethod
    def _context_action(plan: Plan) -> PlanAction:
        return next(a for a in plan.actions if a.kind in ("create_context", "update_context", "replace_context"))

    @staticmethod
    def _manifest_action(plan: Plan) -> PlanAction | None:
        return next((a for a in plan.actions if a.kind in ("create_manifest", "update_manifest")), None)

    def ensure_marked(self, run: OperationRun, action: PlanAction, parent_id: str | None,
                      create: Callable[[], Resource]) -> Resource:
        """Adopt the single resource left by an interrupted attempt, create it, or stop on ambiguity."""
        if not parent_id:
            raise HarnessError("invalid_plan", "La acción no tiene carpeta de destino")
        found = self.drive.find_by_markers(parent_id, run.plan.operation_id, action_id(run.plan, action))
        if len(found) > 1:
            raise OperationConflict("Hay varios recursos con los marcadores de la misma acción",
                                    details={"action": action.kind, "candidates": [item.id for item in found]})
        return found[0] if found else create()

    def recover(self, operation_id: str) -> dict[str, Any]:
        return self.store().load_operation(self.account_id(), operation_id)

    # -- shared helpers -------------------------------------------------------------------------

    def store(self) -> PlanStore:
        if not self.plan_store:
            raise HarnessError("plan_store_unavailable", "Esta instalación no tiene almacén privado de planes")
        return self.plan_store

    def root(self, folder_id: str) -> Resource:
        root = self.drive.get(folder_id)
        if root.mime_type != FOLDER_MIME:
            raise HarnessError("not_folder", "El expediente debe ser una carpeta de Drive")
        if root.trashed:
            raise HarnessError("trashed", "El expediente está en la papelera")
        return root

    def account_id(self) -> str:
        value = self.identity().get("permission_id")
        if not isinstance(value, str) or not value:
            raise HarnessError("identity_unavailable", "Drive no devolvió el ID de la cuenta activa")
        return value

    def performed_by(self) -> str:
        identity = self.identity()
        return str(identity.get("email") or identity.get("permission_id"))

    def _verify_snapshot(self, plan: Plan) -> None:
        """Recheck the plan inputs before (and on resume of) any write.

        Originals are stale only if their MD5 changes, they are trashed or they
        leave the tree.  The root, registered folders and the live offer are
        checked by existence, trash and membership (the offer also by MIME and
        capability), never by Drive ``version``.  Shared state (manifest,
        context) is judged by content and protected by the ETag of ``read``.
        """
        def stale(identifier: str, reason: str) -> HarnessError:
            return HarnessError("stale_plan", "Drive cambió desde la vista previa; prepare un plan nuevo",
                                details={"file_id": identifier, "reason": reason})

        if plan.kind != "incorporation":
            return
        root = self.root(plan.root_folder_id)
        for action in plan.actions:
            if action.kind == "register_original" or (
                    action.kind == "place_original" and action.metadata["strategy"] != "skipped"):
                item = self.drive.get(action.resource_id)
                if item.trashed or not belongs_to_root(self.drive, root, item):
                    raise stale(item.id, "outside_tree_or_trashed")
                if item.md5_checksum != action.expected_version:
                    raise stale(item.id, "content_changed")
            elif action.kind == "register_folder":
                folder = self.drive.get(action.resource_id)
                if folder.mime_type != FOLDER_MIME or not belongs_to_root(self.drive, root, folder):
                    raise stale(folder.id, "outside_tree_or_trashed")
            elif action.kind == "register_external_offer":
                self._external_offer(root, action.resource_id)

    def _external_offer(self, root: Resource, file_id: str) -> Resource:
        offer = self.drive.get(file_id)
        if not belongs_to_root(self.drive, root, offer):
            raise HarnessError("invalid_offer",
                               "La oferta viva debe pertenecer al expediente activo y no estar en la papelera")
        if offer.mime_type != GOOGLE_DOC_MIME:
            raise HarnessError("invalid_offer", "La oferta viva existente debe ser un Google Doc nativo")
        if offer.capabilities and not offer.capabilities.get("canEdit", False):
            raise HarnessError("insufficient_capability", "La cuenta activa no puede editar la oferta viva")
        return offer

    @staticmethod
    def _candidates(tree: list[TreeItem], manifest: Manifest | None) -> dict[str, Any]:
        """Unregistered originals and Google Docs of the whole tree, folders with path and folder suggestions.

        Files inside folders registered for results, offer, deliveries, internal
        material or LitMan state are never original candidates, nor are files inside
        folders written by Core's own Drive publisher (``publication_contract``
        marker): those are listed apart as ``previous_core_outputs``.
        """
        folders = manifest.folders if manifest else {}
        excluded = {folders.get(role) for role in ("initial", "detailed", "offer", "deliveries", "internal", "litman")}
        excluded.discard(None)
        core_folders = [item for item in tree if item.resource.mime_type == FOLDER_MIME
                        and "publication_contract" in item.resource.app_properties]
        excluded |= {item.resource.id for item in core_folders}
        registered = {item["file_id"] for item in manifest.originals} if manifest else set()
        if manifest:  # the source of a copied original stays in place but is already registered
            registered |= {item["copied_from"] for item in manifest.originals if item.get("copied_from")}
            registered |= {identifier for kind, identifier in manifest.references() if kind == "artifact"}
        if manifest and manifest.context_file_id:
            registered.add(manifest.context_file_id)
        if manifest and manifest.live_offer:
            registered.add(manifest.live_offer["document_id"])
        return {
            "originals": [item.resource.id for item in tree
                          if item.resource.mime_type in ALLOWED_MIME_TYPES and item.resource.id not in registered
                          and not excluded & set(item.ancestors)],
            "offer": [item.resource.id for item in tree
                      if item.resource.mime_type == GOOGLE_DOC_MIME and item.resource.id not in registered],
            "folders": [{"id": item.resource.id, "path": item.path} for item in tree
                        if item.resource.mime_type == FOLDER_MIME and item.resource.name != LITMAN_FOLDER
                        and item.resource.id != folders.get("litman")],
            "suggested_folder_ids": suggested_folder_ids(tree, folders),
            "previous_core_outputs": [
                {"folder_id": folder.resource.id, "path": folder.path,
                 "job_type": folder.resource.app_properties.get("job_type"),
                 "files": [{"id": item.resource.id, "path": item.path} for item in tree
                           if folder.resource.id in item.ancestors and item.resource.mime_type != FOLDER_MIME]}
                for folder in core_folders],
        }

    @staticmethod
    def _next_actions(candidates: dict[str, list[str]]) -> list[dict[str, str]]:
        actions: list[dict[str, str]] = []
        if candidates["originals"]:
            actions.append({"kind": "incorporate",
                            "reason": "Hay archivos candidatos; la persona debe seleccionar sus IDs."})
            actions.append({"kind": "identify_originals",
                            "reason": "Los nombres no resuelven qué archivos son originales."})
        else:
            actions.append({"kind": "identify_originals",
                            "reason": "No se encontraron archivos directos; el expediente puede estar incompleto."})
        if candidates["offer"]:
            actions.append({"kind": "identify_live_offer",
                            "reason": "Hay documentos nativos; la oferta viva requiere selección humana."})
        if candidates.get("previous_core_outputs"):
            actions.append({"kind": "review_existing_analysis",
                            "reason": "Hay resultados de un análisis anterior de Core; no se usan como pliegos."})
        elif candidates["folders"]:
            actions.append({"kind": "review_existing_analysis",
                            "reason": "Hay subcarpetas cuya función no se infiere por nombre."})
        return actions

    @staticmethod
    def _status_actions(state: DossierState, candidates: dict[str, list[str]], inspected: list[dict[str, str]],
                        pending: list[dict[str, Any]]) -> list[dict[str, str]]:
        if state.state == "unsupported_manifest":
            return [{"kind": "review_manifest",
                     "reason": "Versión de manifiesto desconocida: sólo lectura hasta actualizar el harness."}]
        if state.state == "partial":
            return [item for item in inspected if item["kind"] != "open_status"] + [
                {"kind": "review_manifest", "reason": state.problem["message"]}]
        if state.manifest is None:
            return inspected
        actions: list[dict[str, str]] = []
        if state.missing:
            actions.append({"kind": "review_missing_resources",
                            "reason": "Hay referencias del manifiesto movidas, en papelera o sin permiso."})
        if state.manifest.originals:
            actions.append({"kind": "run_assessment",
                            "reason": "Hay originales registrados para un análisis inicial."})
            actions.append({"kind": "run_detailed_analysis",
                            "reason": "Hay originales registrados para un análisis detallado."})
        else:
            actions.append({"kind": "identify_originals", "reason": "El expediente no tiene originales registrados."})
        if candidates["originals"]:
            actions.append({"kind": "incorporate", "reason": "Hay archivos sin registrar en la carpeta; regístrelos "
                                                              "sólo si son pliegos u originales."})
        if candidates.get("previous_core_outputs"):
            actions.append({"kind": "review_existing_analysis",
                            "reason": "Hay resultados de un análisis anterior de Core; no se usan como pliegos."})
        if not state.manifest.live_offer and candidates["offer"]:
            actions.append({"kind": "identify_live_offer",
                            "reason": "Hay Google Docs y ninguna oferta viva registrada; requiere selección humana."})
        actions += summary_suggestions(state.manifest)
        if pending:
            actions.append({"kind": "publish_analysis",
                            "reason": "Hay resultados locales validados pendientes de publicar o descartar."})
        return actions
