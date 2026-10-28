"""Core analysis of the connected dossier, published in the same accepted operation when assembled to do so."""
from __future__ import annotations

from datetime import datetime, timezone
import os
import platform
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
from typing import TYPE_CHECKING, Any, Callable

from .. import __version__

from ..adapters import core
from ..adapters.drive import DriveGateway
from ..dossier.models import FOLDER_MIME, Resource
from ..dossier.service import ExpedienteService
from ..errors import HarnessError, safe_exception_message
from ..plans import PlanStore
from ..plans.models import OperationRecord, OperationStatus, Plan, PlanAction
from .inputs import download_originals, require_checksum, validate_original, verify_originals
from .results import REQUIRED_ROLES, includes_technical_document, validate_public_result

if TYPE_CHECKING:  # the publication service imports this module; inject it, never import it
    from ..dossier.publication import PublicationService

LOCAL_VALIDATED = "local_validated"


class AnalysisService:
    """Prepare and run Core locally on originals selected inside the connected dossier."""

    def __init__(self, drive: DriveGateway, plan_store: PlanStore | None = None, *,
                 work_root: Path | None = None, run: core.Runner = subprocess.run,
                 publication: "PublicationService | None" = None,
                 settings: Callable[[], dict[str, Any] | None] | None = None,
                 dossier: ExpedienteService | None = None):
        self.drive = drive
        self.plan_store = plan_store
        self.work_root = work_root
        self.run = run
        # With a publication service the plan includes publishing (one acceptance);
        # without it the analysis stays local (development and isolated tests).
        self.publication = publication
        self.settings = settings or (lambda: None)
        # With a dossier service, preview checks a selected registered original
        # against its manifest MD5 (drift) instead of trusting only Drive's current content.
        self.dossier = dossier

    def preview(self, root_folder_id: str, original_ids: list[str], job_type: str) -> Plan:
        if job_type not in core.JOB_TYPES:
            raise HarnessError("invalid_analysis", "Tipo de análisis no admitido")
        configured = self.settings()
        if not configured:
            raise HarnessError("setup_required", "No hay proveedor configurado; ejecute `setup` antes de analizar",
                               details={"recommended_action": {"tool": "setup"}})
        provider = configured["provider"]
        model = configured.get("model")
        core.validate_provider(provider)
        if not original_ids or len(original_ids) != len(set(original_ids)):
            raise HarnessError("invalid_originals", "Seleccione originales únicos")
        account = self._account_id()
        root = self._root(root_folder_id)
        # Only the content (MD5) of each original identifies the input; the root is
        # rechecked for existence, trash and capability, never by Drive ``version``.
        registered = self._registered_originals(root)
        snapshot: dict[str, str | None] = {}
        actions: list[PlanAction] = []
        for identifier in original_ids:
            item = self.drive.get(identifier)
            validate_original(self.drive, root, item)
            original = registered.get(identifier)
            if original is not None and original.get("status", "active") == "retired":
                raise HarnessError("retired_original_requires_reactivation",
                                   "Este original está retirado; reactívelo con preview_reconciliation antes de "
                                   "analizarlo", details={"file_id": identifier})
            # Same drift comparison as ``status`` (``dossier/service.py:_drift``): any mismatch,
            # including an unexpectedly missing registered checksum, is drift.
            if original is not None and original.get("md5_checksum") != item.md5_checksum:
                raise HarnessError("registered_original_changed",
                                   "El original registrado cambió desde que se registró; revise el expediente "
                                   "con status antes de analizarlo", details={"file_id": identifier,
                                   "registered_md5": original.get("md5_checksum"), "current_md5": item.md5_checksum})
            md5 = require_checksum(item)
            snapshot[item.id] = md5
            actions.append(PlanAction("download_original", item.id, item.name, None, md5,
                                      {"mime_type": item.mime_type, "size": item.size,
                                       "drive_version": item.version, "registered": original is not None}))
        run_core_metadata = {
            "provider": provider, "publication": "included" if self.publication else "local_only",
            "expected_roles": list(REQUIRED_ROLES[job_type]),
            "includes_technical_document": includes_technical_document(job_type)}
        if model is not None:
            run_core_metadata["model"] = model
        actions.append(PlanAction("run_core", None, job_type, None, metadata=run_core_metadata))
        if self.publication:
            actions += self.publication.publication_intent(root.id, job_type)
        plan = Plan("analysis", root.id, account, tuple(actions), snapshot)
        if self.plan_store:
            self.plan_store.save(plan)
        return plan

    def preview_with_candidates(self, root_folder_id: str, original_ids: list[str], job_type: str) -> dict[str, Any]:
        """The stored plan plus other eligible originals not selected, for human awareness (never auto-selected).

        One explicit candidate scan, as the design allows for this already expensive operation;
        execution still only downloads what the accepted plan selected.
        """
        plan = self.preview(root_folder_id, original_ids, job_type)
        other_ids: list[str] = []
        truncated = False
        if self.dossier is not None:
            ids, truncated = self.dossier.unregistered_original_candidates(self._root(root_folder_id))
            other_ids = [identifier for identifier in ids if identifier not in original_ids]
        return {**plan.json(), "other_candidate_original_ids": other_ids, "candidate_scan_truncated": truncated}

    def execute(self, accepted_plan_id: str) -> dict[str, Any]:
        """Run Core only for a previously stored plan of the active account.

        The validated local result is registered in the PlanStore under the
        analysis ``operation_id`` so publication never depends on agent data.
        Repeating an executed plan returns the registered result without rerunning Core.
        """
        store = self._store()
        account = self._account_id()
        # PlanStore.load binds the plan to this ID and the active account.
        plan = store.load(account, accepted_plan_id)
        if plan.kind != "analysis":
            raise HarnessError("invalid_plan", "El plan aceptado no es de análisis")
        existing = store.record(account, plan.operation_id)
        if existing is not None and existing.result is not None:
            result, status = existing.result, existing.status
        else:
            result, status = self._run_core(plan, account), OperationStatus.SUCCEEDED
        response = {**result, "operation_status": str(status)}
        if self.publication and any(action.kind == "publish_results" for action in plan.actions):
            response.update(self._publish(plan, status))
        return response

    def _publish(self, plan: Plan, status: OperationStatus) -> dict[str, Any]:
        """Publish with the publication service; a failure stays recoverable with the same ``plan_id``."""
        retry = {"kind": "publish_analysis", "reason": "La publicación quedó pendiente; repita la ejecución del "
                 "mismo plan para reanudarla sin volver a ejecutar Core.", "tool": "execute_analysis",
                 "arguments": {"plan_id": plan.id}}
        if status == OperationStatus.PUBLISHED:
            return {"publication": {"status": "succeeded", "already_published": True}}
        if status == OperationStatus.DISCARDED:
            return {"publication": {"status": "discarded"}}
        try:
            publication = self.publication.publish_after_analysis(plan.operation_id)
        except HarnessError as exc:
            return {"publication": {"status": "failed", "error": {"code": exc.code, "message": str(exc),
                                                                  "details": exc.details}},
                    "recommended_action": retry}
        if publication.get("status") != "succeeded":
            return {"publication": publication, "recommended_action": retry}
        return {"publication": publication, "recommended_action": publication.get("recommended_action")}

    def _run_core(self, plan: Plan, account: str) -> dict[str, Any]:
        """Download, run Core and register the validated local result (once per plan)."""
        store = self._store()
        run_action = next((action for action in plan.actions if action.kind == "run_core"), None)
        if run_action is None:
            raise HarnessError("invalid_plan", "El plan de análisis no contiene la ejecución de Core")
        job_type = run_action.name
        provider = str(run_action.metadata.get("provider"))
        model = run_action.metadata.get("model")
        core.validate_provider(provider)
        root = self._root(plan.root_folder_id)
        verify_originals(self.drive, root, plan)
        workspace = self._new_workspace()
        try:
            # The input folder name becomes Core's derived job.id (no explicit
            # job.id is sent): it must be unique per run, not a fixed "input",
            # or every publication_id would collide on "input-<timestamp>".
            inputs = workspace / plan.operation_id
            output = workspace / "output"
            inputs.mkdir(mode=0o700)
            output.mkdir(mode=0o700)
            snapshot = download_originals(self.drive, root, plan, inputs)
            config = workspace / "config.toml"
            config.write_text(core.core_config(job_type=job_type, input_dir=inputs,
                                               output_dir=output, provider=provider, model=model), encoding="utf-8")
            payload = core.run_core(config, self.run)
            run_dir = Path(payload["local_path"]).resolve()
            if not run_dir.is_relative_to(output.resolve()):
                raise HarnessError("invalid_core_result", "Core devolvió un run fuera del workspace privado")
            public_artifacts = validate_public_result(payload, run_dir, job_type)
            info = core.core_info(self.run)
            result = {
                "status": LOCAL_VALIDATED, "operation_id": plan.operation_id, "plan_id": plan.id,
                "root_folder_id": plan.root_folder_id, "job_type": job_type, "provider": provider,
                "publication_id": payload["publication_id"], "input_snapshot": snapshot,
                "workspace": str(workspace), "local_path": str(run_dir),
                "public_artifacts": public_artifacts,
                "core_version": info.get("version") if info else None, "harness_version": __version__,
                "performed_by": self._performed_by(),
                "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "recovery": "Resultado local validado; si no se publica, use preview_publication o discard_analysis.",
            }
        except HarnessError as exc:
            exc.details.setdefault("workspace", str(workspace))
            raise
        except Exception as exc:
            raise HarnessError("analysis_failed", "El análisis local falló; el workspace privado se conserva",
                               details={"workspace": str(workspace), "error": safe_exception_message(exc)}) from exc
        # The validated workspace is retained until an accepted publication or discard consumes it.
        store.save_operation(account, plan.operation_id, OperationRecord(
            plan.operation_id, plan.id, "analysis", OperationStatus.SUCCEEDED, result=result))
        return result

    def discard(self, operation_id: str) -> dict[str, Any]:
        """Delete only the local workspace of an unpublished analysis, after the person accepts it."""
        store = self._store()
        account = self._account_id()
        record = store.record(account, operation_id)
        if record is None or record.kind != "analysis" or record.result is None:
            raise HarnessError("unknown_operation", "No existe un análisis local con ese operation_id")
        if record.status != OperationStatus.SUCCEEDED:
            raise HarnessError("invalid_operation_state", "El análisis ya se publicó o descartó",
                               details={"status": str(record.status)})
        remove_workspace(self.work_root, Path(record.result["workspace"]))
        store.save_operation(account, operation_id, OperationRecord(
            record.operation_id, record.plan_id, record.kind, OperationStatus.DISCARDED,
            result={**record.result, "status": "discarded"}))
        return {"status": "discarded", "operation_id": operation_id, "workspace_removed": True, "writes": False}

    def _store(self) -> PlanStore:
        if not self.plan_store:
            raise HarnessError("plan_store_unavailable", "Esta instalación no tiene almacén privado de planes")
        return self.plan_store

    def _performed_by(self) -> str:
        user = self.drive.about().get("user", {})
        return str(user.get("emailAddress") or user.get("permissionId"))

    def _new_workspace(self) -> Path:
        if self.work_root is None:
            raise HarnessError("work_dir_not_configured", "No hay directorio privado de trabajo configurado")
        # New directories are private; an existing configured root keeps its mode
        # and each workspace below it is created 0700.
        self.work_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        workspace = Path(tempfile.mkdtemp(prefix="litman-analysis-", dir=self.work_root))
        if platform.system() != "Windows":
            os.chmod(workspace, 0o700)
        return workspace

    def _registered_originals(self, root: Resource) -> dict[str, dict[str, Any]]:
        """Every manifest-registered original of ``root`` (active or retired), by file ID.

        Empty without a dossier or manifest. One targeted ``load_state`` read, not a full
        ``status`` candidate scan: analysis selection only needs to tell a registered original
        (active or retired) from an unregistered candidate.
        """
        if self.dossier is None:
            return {}
        manifest = self.dossier.load_state(root).manifest
        if manifest is None:
            return {}
        return {item["file_id"]: item for item in manifest.originals}

    def _root(self, folder_id: str) -> Resource:
        root = self.drive.get(folder_id)
        if root.trashed or root.mime_type != FOLDER_MIME:
            raise HarnessError("invalid_root", "La raíz del expediente no es una carpeta disponible")
        if root.capabilities and not root.capabilities.get("canListChildren", False):
            raise HarnessError("insufficient_capability", "La cuenta activa no puede listar el expediente")
        return root

    def _account_id(self) -> str:
        value = self.drive.about().get("user", {}).get("permissionId")
        if not isinstance(value, str) or not value:
            raise HarnessError("identity_unavailable", "Drive no devolvió el ID de la cuenta activa")
        return value


def remove_workspace(work_root: Path | None, workspace: Path) -> None:
    """Remove one analysis workspace, only if it lies inside the configured private work root."""
    if work_root is None:
        raise HarnessError("work_dir_not_configured", "No hay directorio privado de trabajo configurado")
    resolved = workspace.resolve()
    if resolved == work_root.resolve() or not resolved.is_relative_to(work_root.resolve()):
        raise HarnessError("unsafe_workspace", "El workspace registrado no está dentro del directorio de trabajo")
    if resolved.exists():
        if platform.system() == "Windows":
            shutil.rmtree(resolved, onerror=_remove_readonly)
        else:
            shutil.rmtree(resolved)


def _remove_readonly(function: Callable[..., Any], path: str, _exc_info: Any) -> None:
    """Retry only Windows read-only files; other deletion failures still surface."""
    os.chmod(path, stat.S_IWRITE)
    function(path)
