"""Canonical in-container use case for one complete analysis job."""
from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

from litman_core.config import Settings
from litman_core.domain.documents import Document
from litman_core.domain.jobs import JobRequest, JobType, PublishedArtifact, StorageKind
from litman_core.infrastructure.documents.bundle import DocumentBundle
from litman_core.infrastructure.documents.inventory import inventory
from litman_core.infrastructure.documents.normalize import normalize_documents
from litman_core.infrastructure.llm.codex_auth import CodexAuthentication
from litman_core.infrastructure.llm.codex_cli import CodexProvider
from litman_core.infrastructure.storage import GoogleDriveArtifactPublisher, GoogleDriveDocumentSource, LocalArtifactPublisher, LocalDocumentSource
from litman_core.infrastructure.storage.common import publication_inventory
from litman_core.infrastructure.storage.google_drive import build_drive_service
from litman_core.infrastructure.storage.publication import publication_folder_name
from litman_core.pipelines import AssessmentPipeline, DetailedAnalysisPipeline
from litman_core.runtime import initialize_runtime


class ExecutionError(RuntimeError):
    def __init__(self, message: str, local_path: Path):
        super().__init__(message); self.local_path = local_path


@dataclass(frozen=True)
class JobRunnerResult:
    job_id: str
    publication_id: str
    status: str
    local_path: Path
    artifacts: tuple[PublishedArtifact, ...] = ()
    remote: dict[str, Any] | None = None

    @property
    def run_dir(self) -> Path: return self.local_path


class JobRunner:
    def __init__(self, settings: Settings | None = None, *, drive_service_factory: Callable[[Path], Any] = build_drive_service,
                 local_source: Any | None = None, local_publisher: Any | None = None,
                 drive_source_factory: Callable[[Any, int], Any] | None = None,
                 drive_publisher_factory: Callable[[Any], Any] = GoogleDriveArtifactPublisher,
                 provider_factory: Callable[..., Any] = CodexProvider,
                 authentication_factory: Callable[..., Any] = CodexAuthentication.from_environment,
                 assessment_factory: Callable[..., Any] = AssessmentPipeline,
                 detailed_factory: Callable[..., Any] = DetailedAnalysisPipeline,
                 preflight: Callable[[Settings], Any] | None = None) -> None:
        self.settings = settings or Settings(); self.drive_service_factory = drive_service_factory
        self.local_source = local_source or LocalDocumentSource(); self.local_publisher = local_publisher or LocalArtifactPublisher()
        self.drive_source_factory = drive_source_factory or (lambda service, limit: GoogleDriveDocumentSource(service, max_file_mb=limit))
        self.drive_publisher_factory = drive_publisher_factory; self.provider_factory = provider_factory
        self.authentication_factory = authentication_factory; self.assessment_factory = assessment_factory; self.detailed_factory = detailed_factory; self.preflight = preflight

    def run(self, job: JobRequest) -> JobRunnerResult:
        self._validate(job)
        publication_id = publication_folder_name(job.job_id)
        root = job.output_directory.resolve(); root.mkdir(parents=True, exist_ok=True)
        run_dir = root / publication_id
        try: run_dir.mkdir()
        except FileExistsError: raise FileExistsError(f"La carpeta de publicación ya existe: {run_dir}")
        for name in ("input", "output", "logs"): (run_dir / name).mkdir()
        settings = self.settings
        initialize_runtime(home=settings.home_dir, codex_home=settings.codex_home_dir, workspace=settings.workspace_dir, runs=root, output=root, input_dir=Path(job.input_location) if job.input_kind is StorageKind.LOCAL else None)
        workspace = Path(tempfile.mkdtemp(prefix=f"{job.job_id}-", dir=settings.workspace_dir))
        try:
            service = self._drive_service(job)
            source = self.local_source if job.input_kind is StorageKind.LOCAL else self.drive_source_factory(service, settings.max_file_mb)
            materialized = source.materialize(job, workspace); bundle = self._bundle(materialized.directory, materialized.source_metadata, workspace)
            if not any(item.status == "ready" for item in bundle.normalized): raise ValueError("El expediente no produjo documentos normalizados listos para análisis")
            if self.preflight is not None and settings.codex_preflight: self.preflight(settings)
            authentication = self.authentication_factory(codex_home=settings.codex_home_dir)
            provider = self.provider_factory(binary=settings.codex_binary, model=job.codex_model or settings.codex_model, timeout_seconds=settings.codex_timeout_seconds, authentication=authentication, home=settings.home_dir, codex_home=settings.codex_home_dir, tool_failure_policy="warn")
            pipeline = self.assessment_factory(settings, provider) if job.job_type is JobType.ASSESSMENT else self.detailed_factory(settings, provider)
            kwargs = {"case_id": job.job_id, "bundle": bundle, "run_dir": run_dir}
            if job.job_type is JobType.DETAILED_ANALYSIS: kwargs["generation"] = job.options["generation"]
            actual_dir, _ = pipeline.execute(materialized.directory, **kwargs)
            if actual_dir.resolve() != run_dir: raise RuntimeError("El pipeline no usó el directorio de ejecución asignado")
            self._validate_run(job, run_dir)
            catalog = publication_inventory(run_dir, str(job.job_type), job.include_run_files)
            remote = None
            if job.google_drive_folder_id:
                remote_artifacts = self.drive_publisher_factory(service).publish_inventory(job, publication_id, catalog, run_dir=run_dir)
                remote = {"folder_id": job.google_drive_folder_id, "artifacts": [x.uri for x in remote_artifacts]}
            artifacts = self.local_publisher.publish(run_dir, catalog, include_run_files=job.include_run_files)
            return JobRunnerResult(job.job_id, publication_id, "succeeded", run_dir, tuple(artifacts), remote)
        except Exception as exc:
            if isinstance(exc, ExecutionError): raise
            raise ExecutionError(str(exc), run_dir) from exc
        finally: shutil.rmtree(workspace, ignore_errors=True)

    def _drive_service(self, job: JobRequest) -> Any | None:
        if job.input_kind is not StorageKind.GOOGLE_DRIVE and not job.google_drive_folder_id: return None
        if self.settings.google_credentials_file is None: raise ValueError("GOOGLE_APPLICATION_CREDENTIALS es obligatorio para Drive")
        return self.drive_service_factory(self.settings.google_credentials_file)

    def _bundle(self, case_dir: Path, metadata: dict[str, dict[str, Any]], workspace: Path) -> DocumentBundle:
        documents = inventory(case_dir, self.settings.max_file_mb)
        if not documents: raise ValueError(f"El caso no contiene documentos: {case_dir}")
        if metadata: documents = [self._with_source_metadata(document, metadata) for document in documents]
        return DocumentBundle(case_dir, documents, normalize_documents(documents, workspace / "normalized"))

    @staticmethod
    def _with_source_metadata(document: Document, metadata: dict[str, dict[str, Any]]) -> Document:
        source = metadata.get(document.relative_path)
        if source is None: raise ValueError(f"Faltan metadatos Drive para {document.relative_path}")
        return replace(document, document_id=str(source["document_id"]), filename=str(source["filename"]), mime_type=str(source["mime_type"]))

    @staticmethod
    def _validate(job: JobRequest) -> None:
        if job.job_type not in {JobType.ASSESSMENT, JobType.DETAILED_ANALYSIS}: raise ValueError("JobRunner sólo admite assessment o detailed-analysis")

    @staticmethod
    def _validate_run(job: JobRequest, run_dir: Path) -> None:
        output = run_dir / "output"; required = ["validation.json", "result.json"]
        if job.job_type is JobType.DETAILED_ANALYSIS: required.extend(("dossier.json", "generation_manifest.json"))
        missing = [name for name in required if not (output / name).is_file()]
        if missing: raise ValueError(f"El run no contiene: {', '.join(missing)}")
        if json.loads((output / "validation.json").read_text(encoding="utf-8")).get("valid") is not True: raise ValueError("No se publica un run no validado")
