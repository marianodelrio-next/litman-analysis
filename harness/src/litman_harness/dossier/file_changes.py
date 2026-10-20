"""Closed, protected Drive organizing operations for one dossier: create, rename, move, copy, trash,
export and convert, previewed as one plan and applied with capability and protection checks.

The root, local LitMan state, and manifest/context files can never be changed;
manifest-managed resources also cannot be moved or trashed away from their
stable references. Everything else in the connected tree can be organized once
the account's Drive capabilities allow it. Trash never calls ``files.delete``:
the Harness rule is that an original is never removed, only reversibly trashed.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unicodedata
from typing import Any

from ..adapters.documents import DOCX_MIME, PDF_MIME
from ..errors import HarnessError
from ..plans.models import Plan, PlanAction
from .membership import belongs_to_root, in_litman
from .models import FOLDER_MIME, GOOGLE_DOC_MIME, GOOGLE_SHEET_MIME, GOOGLE_SLIDES_MIME, XLSX_MIME, Resource
from .service import ExpedienteService, OperationConflict, OperationRun, action_id
from .tree import LITMAN_FOLDER, walk_tree

MAX_OPERATIONS = 20
MAX_NAME_CHARS = 200
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
MD_MIME, TXT_MIME, CSV_MIME = "text/markdown", "text/plain", "text/csv"

OPERATIONS = {"create_folder": ("parent_folder_id", "name"), "rename": ("file_id", "name"),
              "move": ("file_id", "parent_folder_id"), "copy": ("file_id", "parent_folder_id", "name"),
              "trash": ("file_id",), "export": ("file_id", "format", "parent_folder_id", "name"),
              "convert": ("file_id", "parent_folder_id", "name")}
# A missing capability counts as false (``dict.get(key, False)``); "destination" is the op's parent_folder_id.
CAPABILITIES = {"create_folder": (("destination", "canAddChildren"),),
                "rename": (("item", "canRename"),),
                "move": (("item", "canMoveItemWithinDrive"), ("destination", "canAddChildren")),
                "copy": (("item", "canCopy"), ("destination", "canAddChildren")),
                "trash": (("item", "canTrash"),),
                "export": (("item", "canDownload"), ("destination", "canAddChildren")),
                "convert": (("item", "canDownload"), ("destination", "canAddChildren"))}
EXPORT_FORMATS = {GOOGLE_DOC_MIME: {"pdf": PDF_MIME, "docx": DOCX_MIME, "md": MD_MIME, "txt": TXT_MIME},
                  GOOGLE_SHEET_MIME: {"pdf": PDF_MIME, "xlsx": XLSX_MIME, "csv": CSV_MIME},
                  GOOGLE_SLIDES_MIME: {"pdf": PDF_MIME, "pptx": PPTX_MIME}}
CONVERT_TARGETS = {DOCX_MIME: GOOGLE_DOC_MIME, MD_MIME: GOOGLE_DOC_MIME,
                   XLSX_MIME: GOOGLE_SHEET_MIME, CSV_MIME: GOOGLE_SHEET_MIME}
_CONFLICT_CODES = {"insufficient_permission", "insufficient_capability", "protected_resource", "name_exists",
                   "export_too_large"}
def _invalid(message: str, **details: Any) -> HarnessError:
    return HarnessError("invalid_request", message, details=details)


def validated_operations(operations: Any) -> list[dict[str, Any]]:
    """1-20 closed operations with exact fields; checked here because transports validate only top-level types."""
    if not isinstance(operations, list) or not 1 <= len(operations) <= MAX_OPERATIONS:
        raise _invalid(f"Indique entre 1 y {MAX_OPERATIONS} operaciones")
    clean = []
    for index, operation in enumerate(operations):
        kind = operation.get("op") if isinstance(operation, dict) else None
        if kind not in OPERATIONS:
            raise _invalid("Operación no admitida", operation=index, allowed=list(OPERATIONS))
        fields = OPERATIONS[kind]
        if set(operation) != {"op", *fields}:
            raise _invalid(f"La operación {kind} lleva exactamente los campos op, " + ", ".join(fields),
                           operation=index, fields=list(fields))
        for name in fields:
            value = operation[name]
            if not isinstance(value, str) or not value:
                raise _invalid(f"{name} debe ser texto no vacío", operation=index, field=name)
        clean.append({"op": kind, **{name: operation[name] for name in fields}})
    return clean


def _checked_name(name: str, index: int) -> str:
    if not isinstance(name, str) or not 1 <= len(name) <= MAX_NAME_CHARS:
        raise _invalid(f"name debe ser texto de 1 a {MAX_NAME_CHARS} caracteres", operation=index)
    if any(unicodedata.category(char) == "Cc" for char in name):
        raise _invalid("name contiene caracteres de control", operation=index)
    return name


class FileChangeService:
    def __init__(self, dossier: ExpedienteService):
        self.dossier = dossier
        self.drive = dossier.drive

    # -- plan ------------------------------------------------------------------------------------

    def preview(self, folder_id: str, operations: list[dict[str, Any]]) -> dict[str, Any]:
        """Resolve 1-20 closed organizing operations and store a ``file_changes`` plan; writes nothing."""
        clean = validated_operations(operations)
        root = self.dossier.root(folder_id)
        account = self.dossier.account_id()
        protected = self._protected_ids(root)
        resolved: list[dict[str, Any]] = []
        seen_subjects: set[str] = set()
        taken: dict[str, set[str]] = {}
        for index, operation in enumerate(clean):
            kind = operation["op"]
            item = self._resolve(root, operation["file_id"]) if "file_id" in operation else None
            if item is not None:
                if item.id in seen_subjects:
                    raise _invalid("Un archivo se usó en más de una operación", operation=index, file_id=item.id)
                seen_subjects.add(item.id)
            destination = (self._parent(root, operation["parent_folder_id"])
                           if "parent_folder_id" in operation else None)
            self._check_protected(root, kind, item, protected)
            if kind == "move":
                self._check_not_into_self(item, destination, index)
            name = operation.get("name")
            if name is not None:
                _checked_name(name, index)
            naming_folder, resulting_name = self._naming(root, kind, item, destination, name)
            if naming_folder is not None:
                self._check_name_available(naming_folder, resulting_name, taken,
                                           exclude_id=item.id if kind in ("rename", "move") else None)
            target_mime = self._check_conversion(kind, item, operation.get("format"), index)
            resolved.append({"index": index, "operation": operation, "kind": kind, "item": item,
                             "destination": naming_folder, "name": resulting_name, "target_mime": target_mime})
        self._check_capabilities(resolved)
        actions = tuple(self._action(entry) for entry in resolved)
        previews = [self._preview_entry(root, entry) for entry in resolved]
        plan = Plan("file_changes", root.id, account, actions, {})
        self.dossier.store().save(plan)
        return {**plan.json(), "operations": previews}

    def apply(self, accepted_plan_id: str) -> dict[str, Any]:
        return self.dossier.apply_plan(accepted_plan_id, "file_changes", self._run)

    # -- validation --------------------------------------------------------------------------------

    def _protected_ids(self, root: Resource) -> dict[str, set[str]]:
        """``always`` (root, ``_LitMan`` and below, manifest and context) and ``move_trash`` (manifest references
        and summary sources) protected IDs; ``move_trash`` is checked only for ``move`` and ``trash``."""
        state = self.dossier.load_state(root)
        always = {root.id}
        if state.litman is not None:
            below, _ = walk_tree(self.drive, state.litman)
            always |= {state.litman.id, *(entry.resource.id for entry in below)}
        if state.manifest_file is not None:
            always.add(state.manifest_file.id)
        move_trash: set[str] = set()
        if state.manifest is not None:
            if state.manifest.context_file_id:
                always.add(state.manifest.context_file_id)
            move_trash |= {identifier for _, identifier in state.manifest.references()}
            move_trash |= set(state.manifest.summary_sources())
        return {"always": always, "move_trash": move_trash}

    def _check_protected(self, root: Resource, kind: str, item: Resource | None,
                         protected: dict[str, set[str]]) -> None:
        if item is None:
            return
        if item.id in protected["always"]:
            raise HarnessError("protected_resource", "Ese recurso está protegido y no se puede modificar",
                               details={"file_id": item.id})
        if kind in ("move", "trash") and item.id in protected["move_trash"]:
            raise HarnessError("protected_resource", "Ese recurso está registrado en la licitación y no se puede "
                               "mover ni enviar a la papelera", details={"file_id": item.id})
        if kind == "trash" and item.mime_type == FOLDER_MIME:
            below, _ = walk_tree(self.drive, item)
            descendants = {entry.resource.id for entry in below}
            hit = (protected["always"] | protected["move_trash"]) & descendants
            if hit:
                raise HarnessError("protected_resource", "Esa carpeta contiene recursos protegidos y no se puede "
                                   "enviar a la papelera", details={"file_id": item.id, "protected": sorted(hit)})

    def _check_not_into_self(self, item: Resource, destination: Resource, index: int) -> None:
        if destination.id == item.id or belongs_to_root(self.drive, item, destination):
            raise HarnessError("invalid_move", "No se puede mover un recurso dentro de sí mismo",
                               details={"operation": index, "file_id": item.id})

    def _naming(self, root: Resource, kind: str, item: Resource | None, destination: Resource | None,
               name: str | None) -> tuple[Resource | None, str | None]:
        """The folder whose children must not already carry ``name``, and the resulting name, for this op."""
        if kind == "create_folder":
            return destination, name
        if kind == "rename":
            return self._existing_parent(root, item), name
        if kind == "move":
            return destination, item.name
        if kind in ("copy", "export", "convert"):
            return destination, name
        return None, None  # trash

    def _check_name_available(self, parent: Resource, name: str, taken: dict[str, set[str]], *,
                              exclude_id: str | None) -> None:
        existing = {child.name for child in self.drive.children(parent.id, parent.drive_id)
                   if child.id != exclude_id}
        existing |= taken.get(parent.id, set())
        if name in existing:
            raise HarnessError("name_exists", "La carpeta de destino ya tiene un archivo con ese nombre",
                               details={"parent_folder_id": parent.id, "name": name})
        taken.setdefault(parent.id, set()).add(name)

    def _check_conversion(self, kind: str, item: Resource | None, format_: str | None, index: int) -> str | None:
        if kind == "copy" and item.mime_type == FOLDER_MIME:
            raise HarnessError("unsupported_conversion", "No se puede copiar una carpeta",
                               details={"operation": index})
        if kind == "export":
            allowed = EXPORT_FORMATS.get(item.mime_type, {})
            if format_ not in allowed:
                raise HarnessError("unsupported_conversion", "Ese archivo no se puede exportar a ese formato",
                                   details={"operation": index, "mime_type": item.mime_type,
                                            "allowed": sorted(allowed)})
            return allowed[format_]
        if kind == "convert":
            target = CONVERT_TARGETS.get(item.mime_type)
            if target is None:
                raise HarnessError("unsupported_conversion", "Ese archivo no se puede convertir",
                                   details={"operation": index, "mime_type": item.mime_type})
            return target
        return None

    def _check_capabilities(self, resolved: list[dict[str, Any]]) -> None:
        """One final batch pass: every missing capability is reported together, nothing is planned."""
        violations = []
        for entry in resolved:
            for on, capability in CAPABILITIES[entry["kind"]]:
                target = entry["item"] if on == "item" else entry["destination"]
                if not target.capabilities.get(capability, False):
                    violations.append({"operation": entry["index"], "capability": capability})
        if violations:
            raise HarnessError("insufficient_capability", "La cuenta no tiene permiso para una o más operaciones",
                               details={"violations": violations})

    # -- plan construction -------------------------------------------------------------------------

    @staticmethod
    def _action(entry: dict[str, Any]) -> PlanAction:
        item, destination, kind = entry["item"], entry["destination"], entry["kind"]
        resource_id = item.id if item else None
        parent_id = destination.id if destination else None
        metadata = {"index": entry["index"]}
        if entry["target_mime"] is not None:
            metadata["target_mime_type"] = entry["target_mime"]
            metadata["source_mime_type"] = item.mime_type
        if kind == "export":
            metadata["format"] = entry["operation"]["format"]
        return PlanAction(kind, resource_id, entry["name"] or (item.name if item else ""), parent_id,
                          metadata=metadata)

    def _preview_entry(self, root: Resource, entry: dict[str, Any]) -> dict[str, Any]:
        item, destination = entry["item"], entry["destination"]
        return {**entry["operation"], "source_name": item.name if item else None,
                "source_path": self._path(root, item) if item else None,
                "destination_path": self._path(root, destination) if destination else None,
                "resulting_name": entry["name"]}

    # -- apply ---------------------------------------------------------------------------------------

    def _run(self, run: OperationRun, root: Resource) -> dict[str, Any]:
        plan = run.plan
        for action in plan.actions:
            if run.done(action):
                continue
            handler = getattr(self, f"_apply_{action.kind}")
            output = handler(run, root, action)
            run.complete(action, output)
        return run.envelope("succeeded", writes=True, results=[run.output(a) for a in plan.actions])

    def _conflict(self, run: OperationRun, action: PlanAction, exc: HarnessError) -> OperationConflict:
        return OperationConflict(str(exc), details={"code": exc.code, "operation": action.metadata["index"],
                                                     "completed": list(run.completed), **exc.details})

    def _guarded(self, run: OperationRun, action: PlanAction, fn: Any) -> Any:
        try:
            return fn()
        except HarnessError as exc:
            if exc.code in _CONFLICT_CODES:
                raise self._conflict(run, action, exc) from exc
            raise

    def _reresolve(self, root: Resource, file_id: str, *, ignore_own_trashed: bool = False) -> Resource:
        item = self.drive.get(file_id)
        if item.id != root.id and (not belongs_to_root(self.drive, root, item, ignore_own_trashed=ignore_own_trashed)
                                   or in_litman(self.drive, root, item)):
            raise HarnessError("document_outside_tree", "El archivo ya no está dentro de la licitación conectada",
                               details={"file_id": file_id})
        return item

    def _apply_rename(self, run: OperationRun, root: Resource, action: PlanAction) -> dict[str, Any]:
        item = self._reresolve(root, action.resource_id)
        if item.name == action.name:
            return {"resource_id": item.id}

        def do() -> dict[str, Any]:
            self._revalidate(root, action, item)
            return {"resource_id": self.drive.rename(item.id, action.name).id}
        return self._guarded(run, action, do)

    def _apply_move(self, run: OperationRun, root: Resource, action: PlanAction) -> dict[str, Any]:
        item = self._reresolve(root, action.resource_id)
        if action.parent_id in item.parents:
            return {"resource_id": item.id}

        def do() -> dict[str, Any]:
            self._revalidate(root, action, item)
            return {"resource_id": self.drive.move(item.id, action.parent_id, item.parents).id}
        return self._guarded(run, action, do)

    def _apply_trash(self, run: OperationRun, root: Resource, action: PlanAction) -> dict[str, Any]:
        item = self._reresolve(root, action.resource_id, ignore_own_trashed=True)
        if item.trashed:
            return {"resource_id": item.id}

        def do() -> dict[str, Any]:
            self._revalidate(root, action, item)
            return {"resource_id": self.drive.trash(item.id).id}
        return self._guarded(run, action, do)

    def _apply_create_folder(self, run: OperationRun, root: Resource, action: PlanAction) -> dict[str, Any]:
        created = self.dossier.ensure_marked(run, action, action.parent_id, lambda: self._guarded(
            run, action, lambda: self._create_checked(run, root, action,
                                                       lambda: self.drive.create_folder(
                                                           action.name, action.parent_id, run.plan.operation_id,
                                                           action_id(run.plan, action)))))
        return {"resource_id": created.id}

    def _apply_copy(self, run: OperationRun, root: Resource, action: PlanAction) -> dict[str, Any]:
        source = self._reresolve(root, action.resource_id)
        created = self.dossier.ensure_marked(run, action, action.parent_id, lambda: self._guarded(
            run, action, lambda: self._create_checked(run, root, action, lambda: self.drive.copy(
                source.id, action.name, action.parent_id, run.plan.operation_id, action_id(run.plan, action)))))
        return {"resource_id": created.id}

    def _apply_export(self, run: OperationRun, root: Resource, action: PlanAction) -> dict[str, Any]:
        source = self._reresolve(root, action.resource_id)

        def create() -> Resource:
            with tempfile.TemporaryDirectory(prefix="litman-export-") as directory:
                path = Path(directory) / "export"
                self.drive.export(source.id, action.metadata["target_mime_type"], path)
                return self.drive.upload(action.name, action.parent_id, path, action.metadata["target_mime_type"],
                                         run.plan.operation_id, action_id(run.plan, action))
        created = self.dossier.ensure_marked(run, action, action.parent_id, lambda: self._guarded(
            run, action, lambda: self._create_checked(run, root, action, create)))
        return {"resource_id": created.id}

    def _apply_convert(self, run: OperationRun, root: Resource, action: PlanAction) -> dict[str, Any]:
        source = self._reresolve(root, action.resource_id)

        def create() -> Resource:
            with tempfile.TemporaryDirectory(prefix="litman-convert-") as directory:
                path = Path(directory) / "source"
                self.drive.download(source.id, path)
                return self.drive.upload_converted(action.name, action.parent_id, path,
                                                    action.metadata["source_mime_type"], run.plan.operation_id,
                                                    action_id(run.plan, action),
                                                    target_mime_type=action.metadata["target_mime_type"])
        created = self.dossier.ensure_marked(run, action, action.parent_id, lambda: self._guarded(
            run, action, lambda: self._create_checked(run, root, action, create)))
        return {"resource_id": created.id}

    def _revalidate(self, root: Resource, action: PlanAction, item: Resource) -> None:
        """Re-check protection, capability and ``name_exists`` for a mutating (non-creating) action."""
        protected = self._protected_ids(root)
        self._check_protected(root, action.kind, item, protected)
        destination = self._parent(root, action.parent_id) if action.parent_id else None
        if action.kind == "move":
            self._check_not_into_self(item, destination, action.metadata["index"])
        for on, capability in CAPABILITIES[action.kind]:
            target = item if on == "item" else destination
            if not target.capabilities.get(capability, False):
                raise HarnessError("insufficient_capability", "La cuenta ya no tiene permiso para esta operación",
                                   details={"capability": capability})
        if action.kind == "rename":
            parent = self._existing_parent(root, item)
            self._check_name_available(parent, action.name, {}, exclude_id=item.id)
        elif action.kind == "move":
            self._check_name_available(destination, item.name, {}, exclude_id=item.id)

    def _create_checked(self, run: OperationRun, root: Resource, action: PlanAction, create: Any) -> Resource:
        """Re-check protection, capability and ``name_exists`` (ignoring this action's own markers) before creating."""
        protected = self._protected_ids(root)
        item = self._reresolve(root, action.resource_id) if action.kind != "create_folder" else None
        self._check_protected(root, action.kind, item, protected)
        destination = self._parent(root, action.parent_id)
        for on, capability in CAPABILITIES[action.kind]:
            target = item if on == "item" else destination
            if not target.capabilities.get(capability, False):
                raise HarnessError("insufficient_capability", "La cuenta ya no tiene permiso para esta operación",
                                   details={"capability": capability})
        marker = (run.plan.operation_id, action_id(run.plan, action))
        existing = {child.name for child in self.drive.children(destination.id, destination.drive_id)
                   if not child.has_markers(*marker)}
        if action.name in existing:
            raise HarnessError("name_exists", "La carpeta de destino ya tiene un archivo con ese nombre",
                               details={"parent_folder_id": destination.id, "name": action.name})
        return create()

    # -- shared helpers --------------------------------------------------------------------------

    def _resolve(self, root: Resource, file_id: str) -> Resource:
        item = self.drive.get(file_id)
        if item.id != root.id and (not belongs_to_root(self.drive, root, item) or in_litman(self.drive, root, item)):
            raise HarnessError("document_outside_tree", "El archivo no está dentro de la licitación conectada",
                               details={"file_id": file_id})
        return item

    def _parent(self, root: Resource, folder_id: str) -> Resource:
        folder = root if folder_id == root.id else self.drive.get(folder_id)
        inside = folder.id == root.id or (belongs_to_root(self.drive, root, folder)
                                          and not in_litman(self.drive, root, folder))
        if folder.mime_type != FOLDER_MIME or not inside:
            raise HarnessError("invalid_parent", "La carpeta de destino debe ser una carpeta de la licitación fuera "
                               f"de {LITMAN_FOLDER}", details={"parent_folder_id": folder_id})
        return folder

    def _existing_parent(self, root: Resource, item: Resource) -> Resource:
        """A parent of ``item`` that is itself inside the tree; the root when the item sits directly below it."""
        for parent_id in item.parents:
            if parent_id == root.id:
                return root
            parent = self.drive.get(parent_id)
            if belongs_to_root(self.drive, root, parent):
                return parent
        raise HarnessError("invalid_parent", "No se encontró la carpeta actual del recurso",
                           details={"file_id": item.id})

    def _path(self, root: Resource, item: Resource) -> str:
        if item.id == root.id:
            return ""
        names = [item.name]
        current, seen = item, {item.id}
        while root.id not in current.parents:
            parent = next((candidate for candidate in map(self.drive.get, current.parents)
                           if candidate.id not in seen and belongs_to_root(self.drive, root, candidate)), None)
            if parent is None:
                break
            names.insert(0, parent.name)
            seen.add(parent.id)
            current = parent
        return "/".join(names)
