"""Accepted, resumable repairs of registered dossier resources."""
from __future__ import annotations

from typing import Any

from ..errors import HarnessError
from ..plans.models import Plan, PlanAction
from .file_changes import _checked_name
from .manifest import CONTEXT_NAME, MANIFEST_NAME, Manifest
from .membership import belongs_to_root
from .models import Resource
from .service import ExpedienteService, OperationConflict, OperationRun, now, placement_strategy, placement_warning

_ACTIONS = {'retire_original', 'reactivate_original', 'adopt_current_name', 'rename_managed',
            'place_original', 'return_artifact'}


def _managed(manifest: Manifest, identifier: str) -> tuple[str, dict[str, Any], str | None]:
    for original in manifest.originals:
        if original['file_id'] == identifier:
            return 'original', original, manifest.folders.get('originals')
    for analysis in manifest.analyses:
        if analysis.get('status') == 'published':
            for artifact in analysis.get('artifacts') or []:
                if artifact.get('file_id') == identifier:
                    return 'artifact', artifact, analysis.get('folder_id')
    raise HarnessError('document_not_registered', 'El recurso no está registrado', details={'file_id': identifier})


class ReconciliationService:
    def __init__(self, dossier: ExpedienteService):
        self.dossier, self.drive = dossier, dossier.drive

    def preview(self, folder_id: str, operations: list[dict[str, Any]]) -> Plan:
        if not isinstance(operations, list) or not 1 <= len(operations) <= 20:
            raise HarnessError('invalid_request', 'Indique entre 1 y 20 acciones')
        root = self.dossier.root(folder_id)
        account = self.dossier.account_id()
        state = self.dossier.load_state(root)
        manifest = self.dossier.writable_manifest(state)
        if manifest is None or not manifest.context_file_id:
            raise HarnessError('dossier_not_adopted', 'Incorpore la licitación primero')
        actions = []
        seen = set()
        for index, op in enumerate(operations):
            kind = op.get('op') if isinstance(op, dict) else None
            fields = {'op', 'file_id', 'new_name'} if kind == 'rename_managed' else {'op', 'file_id'}
            if kind not in _ACTIONS or set(op) != fields or not isinstance(op.get('file_id'), str) or not op['file_id']:
                raise HarnessError('invalid_request', 'Acción de reconciliación inválida', details={'operation': index})
            identifier = op['file_id']
            if identifier in seen:
                raise HarnessError('invalid_request', 'Un recurso sólo puede aparecer una vez', details={'file_id': identifier})
            seen.add(identifier)
            category, record, destination = _managed(manifest, identifier)
            active = record.get('status', 'active') == 'active'
            if kind in ('retire_original', 'reactivate_original', 'place_original') and category != 'original':
                raise HarnessError('invalid_request', 'La acción requiere un original')
            if kind == 'return_artifact' and category != 'artifact':
                raise HarnessError('invalid_request', 'La acción requiere un artefacto publicado')
            if (kind == 'retire_original' and not active) or (kind == 'reactivate_original' and active):
                raise HarnessError('invalid_request', 'El original ya tiene ese estado')
            if kind not in ('retire_original', 'reactivate_original') and category == 'original' and not active:
                raise HarnessError('invalid_request', 'El original está retirado')
            item = None
            if kind != 'retire_original':
                item = self.drive.get(identifier)
                if not belongs_to_root(self.drive, root, item):
                    raise HarnessError('document_outside_tree', 'El recurso no está dentro de la licitación')
                if category == 'original' and kind in ('reactivate_original', 'place_original') and (
                        not record.get('md5_checksum') or item.md5_checksum != record.get('md5_checksum')):
                    raise HarnessError('original_changed', 'El original no coincide con el checksum registrado')
            target = op.get('new_name', item.name if item else '')
            if kind == 'rename_managed':
                _checked_name(target, index)
                if not item.capabilities.get('canRename', False):
                    raise HarnessError('insufficient_capability', 'No se puede renombrar el recurso')
            strategy = placement_strategy(item) if kind == 'place_original' else None
            if kind in ('place_original', 'return_artifact'):
                if not destination:
                    raise HarnessError('invalid_manifest', 'No hay carpeta de destino registrada')
                folder = self.drive.get(destination)
                if (not belongs_to_root(self.drive, root, folder) or
                        (strategy != 'in_place' and not folder.capabilities.get('canAddChildren', False))):
                    raise HarnessError('insufficient_capability', 'No se puede usar la carpeta de destino')
                if kind == 'return_artifact' and not item.capabilities.get('canMoveItemWithinDrive', False):
                    raise HarnessError('insufficient_capability', 'No se puede mover el artefacto')
            metadata = {'index': index, 'category': category, 'observed_name': item.name if item else None,
                        'parents': list(item.parents) if item else [], 'destination': destination,
                        'strategy': strategy, 'can_copy': bool(item and item.capabilities.get('canCopy')),
                        'warning': placement_warning(strategy, item.name) if strategy else None}
            actions.append(PlanAction(kind, identifier, target, str(index), item.md5_checksum if item else None, metadata))
        actions.extend((PlanAction('update_context', manifest.context_file_id, CONTEXT_NAME, root.id),
                        PlanAction('update_manifest', state.manifest_file.id, MANIFEST_NAME, None,
                                   metadata={'manifest_sha256': state.manifest_sha256})))
        plan = Plan('reconciliation', root.id, account, tuple(actions), {})
        self.dossier.store().save(plan)
        return plan

    def apply(self, accepted_plan_id: str) -> dict[str, Any]:
        return self.dossier.with_recommendation(self.dossier.apply_plan(accepted_plan_id, 'reconciliation', self._run))

    def _run(self, run: OperationRun, root: Resource) -> dict[str, Any]:
        resumed = self.dossier.resume_after_manifest(run)
        if resumed is not None:
            return resumed
        update = next(a for a in run.plan.actions if a.kind == 'update_manifest')
        base, manifest, version = self.dossier.read_manifest_unchanged(update)
        # Check every affected resource before performing the first Drive mutation.
        for action in run.plan.actions:
            if action.kind in _ACTIONS and action.kind != "retire_original":
                self._check_action(root, manifest, action)
        for action in run.plan.actions:
            if action.kind not in _ACTIONS:
                continue
            category, record, destination = _managed(manifest, action.resource_id)
            if action.kind == 'retire_original':
                record['status'] = 'retired'
                continue
            item, target_state = self._check_action(root, manifest, action)
            if action.kind == 'reactivate_original':
                if item.md5_checksum != record.get('md5_checksum'):
                    raise OperationConflict('El original cambió', details={'file_id': item.id})
                record['status'] = 'active'
            elif action.kind in ('adopt_current_name', 'rename_managed'):
                if action.kind == 'rename_managed' and not target_state:
                    if not item.capabilities.get('canRename', False):
                        raise OperationConflict('No se puede renombrar', details={'file_id': item.id})
                    self.drive.rename(item.id, action.name)
                    run.complete(action, {"resource_id": item.id})
                record['observed_name' if category == 'original' else 'name'] = action.name
            elif action.kind in ('place_original', 'return_artifact'):
                folder = self.drive.get(destination)
                if (not belongs_to_root(self.drive, root, folder) or
                        (action.metadata['strategy'] != 'in_place' and
                         not folder.capabilities.get('canAddChildren', False))):
                    raise OperationConflict('No se puede usar la carpeta de destino', details={'file_id': item.id})
                if action.kind == 'place_original':
                    if not run.done(action):
                        run.complete(action, self.dossier._place_original(run, action, destination))
                    self.dossier._record_placement(manifest, action, run.output(action))
                elif not target_state:
                    if not item.capabilities.get('canMoveItemWithinDrive', False):
                        raise OperationConflict('No se puede mover', details={'file_id': item.id})
                    self.drive.move(item.id, destination, item.parents)
                    run.complete(action, {"resource_id": item.id})
        manifest.history.append({'operation_id': run.plan.operation_id, 'kind': run.plan.kind,
                                 'performed_by': self.dossier.performed_by(), 'completed_at': now()})
        conflict = self.dossier.write_shared_state(run, root, manifest, base, manifest_version=version)
        return self.dossier.shared_result(run, manifest, conflict)

    def _check_action(self, root: Resource, manifest: Manifest, action: PlanAction) -> tuple[Resource, bool]:
        category, _, destination = _managed(manifest, action.resource_id)
        try:
            item = self.drive.get(action.resource_id)
            if not belongs_to_root(self.drive, root, item):
                raise OperationConflict("El recurso ya no está en la licitación", details={"file_id": item.id})
            metadata = action.metadata
            target = ((action.kind == "rename_managed" and item.name == action.name
                       and list(item.parents) == metadata["parents"])
                      or (action.kind in ("place_original", "return_artifact")
                          and list(item.parents) == [destination] and item.name == metadata["observed_name"]))
            original = item.name == metadata["observed_name"] and list(item.parents) == metadata["parents"]
            if not (original or target) or (category == "original" and item.md5_checksum != action.expected_version):
                raise OperationConflict("El recurso cambió desde la vista previa", details={"file_id": item.id})
            if action.kind in ("place_original", "return_artifact"):
                folder = self.drive.get(destination)
                if (not belongs_to_root(self.drive, root, folder) or
                        (metadata["strategy"] != "in_place" and not folder.capabilities.get("canAddChildren", False))):
                    raise OperationConflict("No se puede usar la carpeta de destino", details={"file_id": item.id})
                if not target:
                    strategy = metadata["strategy"] if action.kind == "place_original" else "move"
                    capability = {"move": "canMoveItemWithinDrive", "copy": "canCopy"}.get(strategy)
                    if capability and not item.capabilities.get(capability, False):
                        raise OperationConflict("No se puede aplicar la colocación aceptada", details={"file_id": item.id})
                    if strategy == "move" and metadata.get("can_copy") and not item.capabilities.get("canCopy", False):
                        raise OperationConflict("Cambió el permiso de copia", details={"file_id": item.id})
            if action.kind == "rename_managed" and not target and not item.capabilities.get("canRename", False):
                raise OperationConflict("No se puede renombrar", details={"file_id": item.id})
            return item, target
        except HarnessError as exc:
            if exc.code in ("not_found", "insufficient_permission"):
                raise OperationConflict("El recurso ya no está disponible", details={"file_id": action.resource_id}) from exc
            raise
