from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Callable

from .drive import DriveGateway
from .models import HarnessError, Plan, PlanAction

_NATIVE = "application/vnd.google-apps."
_ALLOWED = {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel", "text/plain"}
_PROVIDERS = {"codex", "claude-code"}


class AnalysisService:
    """Local Core invocation.  Publishing is deliberately unavailable until the Drive concurrency gate is proven."""
    def __init__(self, drive: DriveGateway, run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run):
        self.drive, self.run = drive, run

    def preview(self, root_folder_id: str, original_ids: list[str], job_type: str, account_id: str) -> Plan:
        if job_type not in {"assessment", "detailed-analysis"}: raise HarnessError("invalid_analysis", "Tipo de análisis no admitido")
        if not original_ids or len(original_ids) != len(set(original_ids)): raise HarnessError("invalid_originals", "Seleccione originales únicos")
        root = self.drive.get(root_folder_id)
        if root.trashed or root.mime_type != "application/vnd.google-apps.folder": raise HarnessError("invalid_root", "La raíz del expediente no es una carpeta disponible")
        if root.capabilities and not root.capabilities.get("canListChildren", False): raise HarnessError("insufficient_capability", "La cuenta activa no puede listar el expediente")
        snapshot: dict[str, str | None] = {root.id: root.version}
        actions: list[PlanAction] = []
        for identifier in original_ids:
            item = self.drive.get(identifier)
            self._validate_original(root, item)
            snapshot[item.id] = item.version
            actions.append(PlanAction("download_original", item.id, item.name, None, item.version, {"mime_type": item.mime_type, "size": item.size}))
        actions.append(PlanAction("run_core", None, job_type, None, metadata={"publication": "local_only", "expected_catalog": self._catalog(job_type)}))
        return Plan("analysis", root_folder_id, account_id, tuple(actions), snapshot)

    def execute_local(self, plan: Plan, accepted_plan_id: str, provider: str, work_root: Path | None = None) -> dict:
        if plan.id != accepted_plan_id: raise HarnessError("plan_not_accepted", "El identificador de plan no coincide con la vista previa")
        if provider not in _PROVIDERS: raise HarnessError("invalid_provider", "Proveedor Core no autorizado")
        root = self.drive.get(plan.root_folder_id)
        if root.version != plan.snapshot.get(root.id): raise HarnessError("stale_plan", "La raíz del expediente cambió antes de ejecutar Core")
        for identifier, version in plan.snapshot.items():
            if identifier == root.id: continue
            current = self.drive.get(identifier)
            if current.version != version: raise HarnessError("stale_plan", "Un original cambió antes de ejecutar Core", details={"file_id": identifier})
            self._validate_original(root, current)
        workspace = Path(tempfile.mkdtemp(prefix="litman-harness-", dir=work_root))
        os.chmod(workspace, 0o700)
        succeeded = False
        try:
            inputs = workspace / "input"; output = workspace / "output"; inputs.mkdir(mode=0o700); output.mkdir(mode=0o700)
            snapshot = []
            for action in plan.actions:
                if action.kind != "download_original": continue
                target = inputs / f"{action.resource_id}-{Path(action.name).name}"
                self.drive.download(action.resource_id or "", target)
                snapshot.append({"file_id": action.resource_id, "name": action.name, "sha256": _sha256(target), "size": target.stat().st_size})
            for item in snapshot:
                current = self.drive.get(item["file_id"])
                if current.version != plan.snapshot[item["file_id"]]: raise HarnessError("stale_plan", "Un original cambió durante la descarga")
                self._validate_original(root, current)
            job_type = next(action.name for action in plan.actions if action.kind == "run_core")
            config = workspace / "config.toml"
            # JSON string escaping is valid TOML basic-string escaping for these
            # scalar values and prevents a local path from changing the config.
            config.write_text("[job]\nid = %s\ntype = %s\n[input]\nkind = %s\nlocation = %s\n[output]\ndirectory = %s\n[publication]\ninclude_run_files = false\n[llm]\nprovider = %s\n" % tuple(
                json.dumps(value) for value in (plan.operation_id, job_type, "local", str(inputs), str(output), provider)
            ), encoding="utf-8")
            result = self.run(["litman-core", "run", "--config", str(config)], text=True, capture_output=True, check=False)
            if result.returncode: raise HarnessError("core_failed", "LitMan Core falló; el run local se conserva para diagnóstico", details={"workspace": str(workspace), "stderr": result.stderr[-1000:]})
            try: payload = json.loads(result.stdout)
            except json.JSONDecodeError as exc: raise HarnessError("invalid_core_result", "Core no devolvió JSON válido") from exc
            if payload.get("status") != "succeeded" or not payload.get("publication_id") or not isinstance(payload.get("local_path"), str): raise HarnessError("invalid_core_result", "Core no devolvió una publicación validada")
            self._validate_run(Path(payload["local_path"]), job_type)
            succeeded = True
            # Publication needs an atomic manifest/context strategy; do not claim a Drive success yet.
            return {"status": "local_validated_pending_publication_gate", "operation_id": plan.operation_id, "publication_id": payload["publication_id"], "input_snapshot": snapshot,
                    "local_path": payload["local_path"], "recovery": "La publicación Drive está deshabilitada hasta verificar la precondición atómica."}
        except HarnessError as exc:
            exc.details.setdefault("workspace", str(workspace))
            raise
        except Exception as exc:
            raise HarnessError("analysis_failed", "El análisis local falló; el workspace privado se conserva", details={"workspace": str(workspace), "error": str(exc)}) from exc
        finally:
            if succeeded:
                import shutil
                shutil.rmtree(workspace, ignore_errors=True)
            # Failure retains the private workspace for diagnosis/retry, reported in
            # the HarnessError details instead of falsely promising retention.

    @staticmethod
    def _validate_original(root, item) -> None:
        if item.trashed or root.id not in item.parents or item.drive_id != root.drive_id:
            raise HarnessError("outside_expediente", "El original debe pertenecer a la raíz y unidad compartida del expediente")
        if item.capabilities and not item.capabilities.get("canDownload", False): raise HarnessError("insufficient_capability", "La cuenta activa no puede descargar un original")
        if item.mime_type.startswith(_NATIVE): raise HarnessError("native_google_file", "Los originales nativos de Google no se exportan implícitamente")
        if item.mime_type not in _ALLOWED: raise HarnessError("unsupported_mime", f"Formato no admitido: {item.mime_type}")

    @staticmethod
    def _validate_run(run_dir: Path, job_type: str) -> None:
        output = run_dir / "output"; validation = output / "validation.json"
        try: valid = json.loads(validation.read_text(encoding="utf-8")).get("valid") is True
        except (OSError, json.JSONDecodeError) as exc: raise HarnessError("invalid_core_result", "validation.json no es legible") from exc
        if not valid: raise HarnessError("invalid_core_result", "Core produjo un run no validado")
        if job_type == "assessment": expected = {"ficha_oportunidad.pdf"}
        else:
            manifest_path = output / "generation_manifest.json"
            try: manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc: raise HarnessError("invalid_core_result", "Falta generation_manifest.json válido") from exc
            technical = [Path(item).name for artifact in manifest.get("artifacts", []) if artifact.get("id") == "technical-document" for item in artifact.get("documents", []) if str(item).endswith(".docx")]
            if len(technical) != 1: raise HarnessError("invalid_core_result", "El manifiesto no declara un único DOCX técnico")
            expected = {"resumen_tecnico.docx", "guia_preparacion_oferta.docx", "simulador_economico.xlsx", technical[0]}
        # A run deliberately contains validation, lineage and diagnostic material.
        # Only the closed public contract controls publication; extra local files
        # must not turn a valid run into a failure or become publishable.
        missing = sorted(name for name in expected if not (output / name).is_file())
        if missing: raise HarnessError("invalid_core_result", "Faltan artefactos del catálogo público de Core", details={"missing": missing})

    @staticmethod
    def _catalog(job_type: str) -> list[str]:
        return ["ficha_oportunidad.pdf"] if job_type == "assessment" else ["resumen_tecnico.docx", "guia_preparacion_oferta.docx", "technical-document (de generation_manifest.json)", "simulador_economico.xlsx"]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): digest.update(block)
    return digest.hexdigest()
