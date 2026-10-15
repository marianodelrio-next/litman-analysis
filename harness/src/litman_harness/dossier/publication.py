"""Publication of a validated local Core result into the connected dossier (decision 7).

The result is read from the local PlanStore record of the analysis, never from
agent input.  Uploads go directly to destinations by ID inside the dossier.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..analysis.inputs import sha256_file
from ..analysis.results import MIME_TYPES, TECHNICAL_DOCUMENT_ID
from ..analysis.service import remove_workspace
from ..errors import HarnessError
from ..plans.models import OperationRecord, OperationStatus, Plan, PlanAction
from .manifest import CONTEXT_NAME, MANIFEST_NAME, Manifest, advanced_phase
from .membership import belongs_to_root
from .models import FOLDER_MIME, GOOGLE_DOC_MIME, Resource
from .service import ExpedienteService, OperationConflict, OperationRun, action_id, now, summary_suggestions

_PHASE_FOLDER = {"assessment": "initial", "detailed-analysis": "detailed"}


class PublicationService:
    def __init__(self, dossier: ExpedienteService, work_root: Path | None = None):
        self.dossier = dossier
        self.drive = dossier.drive
        self.work_root = work_root

    def publication_intent(self, root_folder_id: str, job_type: str) -> list[PlanAction]:
        """What publishing an analysis of ``job_type`` will need, validated before Core runs.

        Fails early (adoption, phase folder, offer folder) so a missing requirement
        never surfaces after minutes of analysis.
        """
        root = self.dossier.root(root_folder_id)
        state = self.dossier.load_state(root)
        manifest = state.manifest
        if manifest is None or state.state not in ("adopted", "degraded"):
            raise HarnessError("dossier_not_adopted", "Incorpore la licitación antes de analizarla y publicar",
                               details={"state": state.state})
        role = _PHASE_FOLDER[job_type]
        actions = [PlanAction("publish_results", None, role, self._registered_folder(root, manifest, role).id)]
        if job_type == "detailed-analysis" and manifest.live_offer is None:
            actions.append(PlanAction("convert_live_offer", None, "oferta viva",
                                      self._registered_folder(root, manifest, "offer").id))
        target = advanced_phase(manifest.workflow_phase, job_type)
        if target:
            actions.append(PlanAction("set_phase", None, target, None, metadata={"previous": manifest.workflow_phase}))
        actions.append(PlanAction("update_context", manifest.context_file_id, CONTEXT_NAME, root.id))
        actions.append(PlanAction("update_manifest", state.manifest_file.id, MANIFEST_NAME, None))
        return actions

    def publish_after_analysis(self, analysis_operation_id: str) -> dict[str, Any]:
        """Publish an executed analysis under the acceptance of its analysis plan (no second acceptance).

        The publication plan is created once and linked from the analysis record,
        so repeating ``execute_analysis`` resumes the same publication.
        """
        store = self.dossier.store()
        account = self.dossier.account_id()
        record = self._analysis(account, analysis_operation_id)
        plan_id = record.result.get("publication_plan_id")
        if not plan_id:
            plan_id = self.preview(analysis_operation_id).id
            store.save_operation(account, analysis_operation_id, OperationRecord(
                record.operation_id, record.plan_id, record.kind, record.status,
                result={**record.result, "publication_plan_id": plan_id}))
        return self.apply(plan_id)

    def preview(self, analysis_operation_id: str) -> Plan:
        """Plan the run folder, uploads, optional live-offer conversion, phase and shared-state updates."""
        store = self.dossier.store()
        account = self.dossier.account_id()
        analysis = self._analysis(account, analysis_operation_id)
        result = analysis.result
        root = self.dossier.root(result["root_folder_id"])
        state = self.dossier.load_state(root)
        manifest = state.manifest
        if manifest is None or state.state not in ("adopted", "degraded"):
            raise HarnessError("dossier_not_adopted", "Incorpore la licitación antes de publicar resultados",
                               details={"state": state.state})
        if any(item.get("operation_id") == analysis_operation_id for item in manifest.analyses):
            raise HarnessError("already_published", "Ese análisis ya figura en el manifiesto")
        phase_folder = self._registered_folder(root, manifest, _PHASE_FOLDER[result["job_type"]])
        self._verify_local(result)
        actions = [PlanAction("create_run_folder", None, f"{result['completed_at'][:10]} {result['publication_id']}",
                              phase_folder.id, metadata={"role": "run_folder"})]
        for artifact in result["public_artifacts"]:
            actions.append(PlanAction("upload_public_artifact", None, artifact["name"], None, metadata={
                "role": artifact["role"], "sha256": artifact["sha256"], "mime_type": artifact["mime_type"]}))
        if result["job_type"] == "detailed-analysis" and manifest.live_offer is None:
            offer_folder = self._registered_folder(root, manifest, "offer")
            technical = next(item for item in result["public_artifacts"] if item["role"] == TECHNICAL_DOCUMENT_ID)
            actions.append(PlanAction("convert_live_offer", None, Path(technical["name"]).stem, offer_folder.id,
                                      metadata={"artifact": technical["name"], "sha256": technical["sha256"]}))
        target = advanced_phase(manifest.workflow_phase, result["job_type"])
        if target:
            actions.append(PlanAction("set_phase", None, target, None, metadata={"previous": manifest.workflow_phase}))
        actions.append(PlanAction("update_context", manifest.context_file_id, CONTEXT_NAME, root.id))
        # The apply merges into the manifest current at that moment (additive), so
        # the plan pins no manifest version; local hashes and folders are rechecked.
        actions.append(PlanAction("update_manifest", state.manifest_file.id, MANIFEST_NAME, None,
                                  metadata={"analysis_operation_id": analysis_operation_id}))
        plan = Plan("publication", root.id, account, tuple(actions), {})
        store.save(plan)
        return plan

    def apply(self, accepted_plan_id: str) -> dict[str, Any]:
        return self.dossier.with_recommendation(self.dossier.apply_plan(accepted_plan_id, "publication", self._run))

    def _run(self, run: OperationRun, root: Resource) -> dict[str, Any]:
        plan = run.plan
        update = next(a for a in plan.actions if a.kind == "update_manifest")
        analysis_id = update.metadata["analysis_operation_id"]
        resumed = self.dossier.resume_after_manifest(run)
        if resumed is not None:
            self._finalize(run, analysis_id)
            return resumed
        # Read the manifest current now; publication merges additively into it.
        content, version = self.dossier.shared_state.read(update.resource_id)
        base = Manifest.parse(content)
        manifest = Manifest.parse(content)
        if any(item.get("operation_id") == analysis_id for item in manifest.analyses):
            self._finalize(run, analysis_id)
            return self.dossier.shared_result(run, manifest, None, already_registered=True)
        result = self._analysis(run.account, analysis_id).result
        self._verify_local(result)
        self._check_folders(run, manifest, result["job_type"])
        local = {item["name"]: item for item in result["public_artifacts"]}
        run_folder = None
        artifacts = []
        live_offer = None
        for action in plan.actions:
            aid = action_id(plan, action)
            if action.kind == "create_run_folder":
                if not run.done(action):
                    created = self.dossier.ensure_marked(run, action, action.parent_id, lambda a=action, i=aid: (
                        self.drive.create_folder(a.name, a.parent_id, plan.operation_id, i)))
                    self._check_created(root, created, action.parent_id, FOLDER_MIME)
                    run.complete(action, {"resource_id": created.id})
                run_folder = run.output(action)["resource_id"]
            elif action.kind == "upload_public_artifact":
                if not run.done(action):
                    source = Path(local[action.name]["path"])
                    created = self.dossier.ensure_marked(run, action, run_folder, lambda a=action, i=aid, p=source: (
                        self.drive.upload(a.name, run_folder, p, a.metadata["mime_type"], plan.operation_id, i)))
                    self._check_created(root, created, run_folder, None)
                    run.complete(action, {"resource_id": created.id})
                artifacts.append({"role": action.metadata["role"], "name": action.name,
                                  "file_id": run.output(action)["resource_id"], "sha256": action.metadata["sha256"]})
            elif action.kind == "convert_live_offer":
                if manifest.live_offer is not None and not run.done(action):
                    continue  # registered meanwhile: the DOCX stays only as an artifact
                if not run.done(action):
                    source = Path(local[action.metadata["artifact"]]["path"])
                    created = self.dossier.ensure_marked(
                        run, action, action.parent_id, lambda a=action, i=aid, p=source: self.drive.upload_converted(
                            a.name, a.parent_id, p, MIME_TYPES[".docx"], plan.operation_id, i))
                    self._check_created(root, created, action.parent_id, GOOGLE_DOC_MIME)
                    run.complete(action, {"resource_id": created.id})
                origin = next((item["file_id"] for item in artifacts if item["role"] == TECHNICAL_DOCUMENT_ID), None)
                live_offer = {"document_id": run.output(action)["resource_id"], "origin_kind": "core_conversion",
                              "origin_analysis_id": analysis_id, "origin_artifact_id": origin,
                              "registered_by": self.dossier.performed_by()}
        performed_by = self.dossier.performed_by()
        sources = [{"file_id": item["file_id"], "drive_version": item.get("drive_version"),
                    "md5_checksum": item.get("md5_checksum"), "sha256": item["sha256"]}
                   for item in result["input_snapshot"]]
        for original in manifest.originals:
            for source in sources:
                if (original["file_id"] == source["file_id"] and original.get("sha256") is None
                        and source["md5_checksum"] and original.get("md5_checksum") == source["md5_checksum"]):
                    original["sha256"] = source["sha256"]
        manifest.analyses.append({
            "operation_id": analysis_id, "publication_id": result["publication_id"], "type": result["job_type"],
            "provider": result["provider"], "core_version": result.get("core_version"),
            "harness_version": result.get("harness_version"), "performed_by": result.get("performed_by"),
            "source_originals": sources, "folder_id": run_folder, "artifacts": artifacts, "status": "published"})
        if live_offer and manifest.live_offer is None:
            manifest.live_offer = live_offer
        for action in plan.actions:
            # Re-evaluated on the current manifest: the phase only ever advances.
            if action.kind == "set_phase" and advanced_phase(manifest.workflow_phase, result["job_type"]):
                manifest.workflow_phase = action.name
        manifest.history.append({"operation_id": plan.operation_id, "kind": plan.kind, "performed_by": performed_by,
                                 "completed_at": now()})
        try:
            context_conflict = self.dossier.write_shared_state(run, root, manifest, base, manifest_version=version)
        except HarnessError as exc:
            if exc.code != "concurrent_change":
                raise
            raise HarnessError("manifest_changed_retry", "manifest.json cambió durante la publicación; repita la "
                               "aceptación para reanudar sin volver a subir nada",
                               details={"operation_id": plan.operation_id}) from exc
        self._finalize(run, analysis_id)
        return self.dossier.shared_result(run, manifest, context_conflict, run_folder_id=run_folder,
                                          next_actions=summary_suggestions(manifest),
                                          artifacts=artifacts, live_offer=manifest.live_offer)

    @staticmethod
    def _check_folders(run: OperationRun, manifest: Manifest, job_type: str) -> None:
        """Pending destinations must still be the registered phase and offer folders."""
        expected = {"create_run_folder": _PHASE_FOLDER[job_type], "convert_live_offer": "offer"}
        for action in run.plan.actions:
            role = expected.get(action.kind)
            if not role or run.done(action) or (role == "offer" and manifest.live_offer is not None):
                continue
            if manifest.folders.get(role) != action.parent_id:
                raise OperationConflict("La carpeta de destino ya no es la registrada en el manifiesto",
                                        details={"action": action.kind, "role": role})

    def _finalize(self, run: OperationRun, analysis_id: str) -> None:
        """Mark the local analysis as published and delete its workspace (decision 8)."""
        record = run.store.record(run.account, analysis_id)
        if record is None or record.status == OperationStatus.PUBLISHED:
            return
        remove_workspace(self.work_root, Path(record.result["workspace"]))
        run.store.save_operation(run.account, analysis_id, OperationRecord(
            record.operation_id, record.plan_id, record.kind, OperationStatus.PUBLISHED,
            result={**record.result, "status": "published", "publication_operation_id": run.plan.operation_id}))

    def _analysis(self, account: str, operation_id: str) -> OperationRecord:
        record = self.dossier.store().record(account, operation_id)
        if record is None or record.kind != "analysis" or not record.result:
            raise HarnessError("unknown_operation", "No existe un análisis local con ese operation_id")
        if record.status != OperationStatus.SUCCEEDED:
            raise HarnessError("invalid_operation_state", "El análisis ya se publicó o se descartó",
                               details={"status": str(record.status)})
        return record

    def _registered_folder(self, root: Resource, manifest: Manifest, role: str) -> Resource:
        identifier = manifest.folders.get(role)
        if not identifier:
            raise HarnessError("folder_not_registered", "La carpeta necesaria no está registrada en el expediente",
                               details={"role": role})
        folder = self.drive.get(identifier)
        if folder.mime_type != FOLDER_MIME or not belongs_to_root(self.drive, root, folder):
            raise HarnessError("folder_not_registered", "La carpeta registrada ya no está en la licitación",
                               details={"role": role, "id": identifier})
        return folder

    def _check_created(self, root: Resource, created: Resource, parent_id: str, mime_type: str | None) -> None:
        if parent_id not in created.parents or not belongs_to_root(self.drive, root, created):
            raise HarnessError("invalid_created_resource", "Drive creó un recurso fuera de su destino")
        if mime_type and created.mime_type != mime_type:
            raise HarnessError("invalid_created_resource", "El recurso creado no tiene el tipo esperado",
                               details={"expected": mime_type, "actual": created.mime_type})

    @staticmethod
    def _verify_local(result: dict[str, Any]) -> None:
        for artifact in result["public_artifacts"]:
            path = Path(artifact["path"])
            if not path.is_file() or sha256_file(path) != artifact["sha256"]:
                raise HarnessError("local_artifact_changed", "Un artefacto local cambió o falta; no se publica",
                                   details={"name": artifact["name"]})
