"""Canonical in-container use case for one complete analysis job."""
from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

from litman_analysis.config import Settings
from litman_analysis.domain.documents import Document
from litman_analysis.domain.jobs import JobRequest, JobType, PublishedArtifact, StorageKind
from litman_analysis.infrastructure.documents.bundle import DocumentBundle
from litman_analysis.infrastructure.documents.inventory import inventory
from litman_analysis.infrastructure.documents.normalize import normalize_documents
from litman_analysis.infrastructure.llm.codex_auth import CodexAuthentication
from litman_analysis.infrastructure.llm.codex_cli import CodexProvider
from litman_analysis.infrastructure.storage import GoogleDriveArtifactPublisher, GoogleDriveDocumentSource, LocalArtifactPublisher, LocalDocumentSource
from litman_analysis.infrastructure.storage.google_drive import build_drive_service
from litman_analysis.pipelines import AssessmentPipeline, DetailedAnalysisPipeline
from litman_analysis.runtime import initialize_runtime


@dataclass(frozen=True)
class JobRunnerResult:
    job_id: str
    status: str
    run_dir: Path
    diagnostics_dir: Path
    artifacts: tuple[PublishedArtifact, ...] = ()

    @property
    def execution_dir(self) -> Path:
        return self.run_dir


class JobRunner:
    """Materialize, normalize, analyze, validate and publish in one process."""

    def __init__(self, settings: Settings | None = None, *, drive_service_factory: Callable[[Path], Any] = build_drive_service,
                 local_source: Any | None = None, local_publisher: Any | None = None,
                 drive_source_factory: Callable[[Any, int], Any] | None = None,
                 drive_publisher_factory: Callable[[Any], Any] = GoogleDriveArtifactPublisher,
                 provider_factory: Callable[..., Any] = CodexProvider,
                 authentication_factory: Callable[..., Any] = CodexAuthentication.from_environment,
                 assessment_factory: Callable[..., Any] = AssessmentPipeline,
                 detailed_factory: Callable[..., Any] = DetailedAnalysisPipeline,
                 preflight: Callable[[Settings], Any] | None = None) -> None:
        self.settings = settings or Settings()
        self.drive_service_factory = drive_service_factory
        self.local_source = local_source or LocalDocumentSource()
        self.local_publisher = local_publisher or LocalArtifactPublisher()
        self.drive_source_factory = drive_source_factory or (lambda service, limit: GoogleDriveDocumentSource(service, max_file_mb=limit))
        self.drive_publisher_factory = drive_publisher_factory
        self.provider_factory = provider_factory
        self.authentication_factory = authentication_factory
        self.assessment_factory = assessment_factory
        self.detailed_factory = detailed_factory
        self.preflight = preflight

    def run(self, job: JobRequest) -> JobRunnerResult:
        self._validate(job)
        settings = self.settings
        initialize_runtime(home=settings.home_dir, codex_home=settings.codex_home_dir,
                           workspace=settings.workspace_dir, runs=settings.runs_dir,
                           output=Path(job.output_location) if job.output_kind is StorageKind.LOCAL else None,
                           input_dir=Path(job.input_location) if job.input_kind is StorageKind.LOCAL else None)
        workspace = Path(tempfile.mkdtemp(prefix=f"{job.job_id}-", dir=settings.workspace_dir))
        try:
            service = self._drive_service(job)
            source = self.local_source if job.input_kind is StorageKind.LOCAL else self.drive_source_factory(service, settings.max_file_mb)
            materialized = source.materialize(job, workspace)
            bundle = self._bundle(materialized.directory, materialized.source_metadata, workspace)
            if not any(item.status == "ready" for item in bundle.normalized):
                raise ValueError("El expediente no produjo documentos normalizados listos para análisis")
            if self.preflight is not None and settings.codex_preflight:
                self.preflight(settings)
            authentication = self.authentication_factory(codex_home=settings.codex_home_dir)
            provider = self.provider_factory(binary=settings.codex_binary, model=settings.codex_model,
                timeout_seconds=settings.codex_timeout_seconds, authentication=authentication,
                home=settings.home_dir, codex_home=settings.codex_home_dir, tool_failure_policy="warn")
            if job.job_type is JobType.ASSESSMENT:
                run_dir, _ = self.assessment_factory(settings, provider).execute(materialized.directory, case_id=job.job_id, bundle=bundle)
            else:
                run_dir, _ = self.detailed_factory(settings, provider).execute(materialized.directory, case_id=job.job_id,
                    generation=job.options.get("generation"), bundle=bundle)
            self._validate_run(job, run_dir)
            publisher = self.local_publisher if job.output_kind is StorageKind.LOCAL else self.drive_publisher_factory(service)
            try:
                artifacts = publisher.publish(job, run_dir)
            except Exception as exc:
                if "storageQuotaExceeded" in str(exc):
                    raise RuntimeError("Google Drive devolvió storageQuotaExceeded; publique en un Shared Drive con cuota disponible") from exc
                raise
            return JobRunnerResult(job.job_id, "succeeded", run_dir, run_dir, tuple(artifacts))
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    def _drive_service(self, job: JobRequest) -> Any | None:
        if StorageKind.GOOGLE_DRIVE not in (job.input_kind, job.output_kind):
            return None
        if self.settings.google_credentials_file is None:
            raise ValueError("GOOGLE_APPLICATION_CREDENTIALS es obligatorio para Drive")
        return self.drive_service_factory(self.settings.google_credentials_file)

    def _bundle(self, case_dir: Path, metadata: dict[str, dict[str, Any]], workspace: Path) -> DocumentBundle:
        documents = inventory(case_dir, self.settings.max_file_mb)
        if not documents:
            raise ValueError(f"El caso no contiene documentos: {case_dir}")
        if metadata:
            documents = [self._with_source_metadata(document, metadata) for document in documents]
        normalized = normalize_documents(documents, workspace / "normalized")
        return DocumentBundle(case_dir, documents, normalized)

    @staticmethod
    def _with_source_metadata(document: Document, metadata: dict[str, dict[str, Any]]) -> Document:
        source = metadata.get(document.relative_path)
        if source is None:
            raise ValueError(f"Faltan metadatos Drive para {document.relative_path}")
        return replace(document, document_id=str(source["document_id"]), filename=str(source["filename"]), mime_type=str(source["mime_type"]))

    @staticmethod
    def _validate(job: JobRequest) -> None:
        supported = {(source, destination)
                     for source in StorageKind for destination in StorageKind}
        if job.job_type not in {JobType.ASSESSMENT, JobType.DETAILED_ANALYSIS}:
            raise ValueError("JobRunner sólo admite assessment o detailed-analysis")
        if (job.input_kind, job.output_kind) not in supported:
            raise ValueError("Combinación de almacenamiento no soportada por JobRunner")

    @staticmethod
    def _validate_run(job: JobRequest, run_dir: Path) -> None:
        output = run_dir / "output"
        required = ["validation.json", "result.json"]
        if job.job_type is JobType.DETAILED_ANALYSIS:
            required.extend(("dossier.json", "generation_manifest.json"))
        missing = [name for name in required if not (output / name).is_file()]
        if missing:
            raise ValueError(f"El run no contiene: {', '.join(missing)}")
        if (job.job_type is JobType.ASSESSMENT
                and job.output_kind is StorageKind.GOOGLE_DRIVE
                and not (output / "ficha_oportunidad.pdf").is_file()):
            raise ValueError("El run assessment no contiene output/ficha_oportunidad.pdf para publicar en Drive")
        validation = json.loads((output / "validation.json").read_text(encoding="utf-8"))
        if validation.get("valid") is not True:
            raise ValueError("No se publica un run no validado")
        if job.job_type is JobType.DETAILED_ANALYSIS:
            manifest = json.loads((output / "generation_manifest.json").read_text(encoding="utf-8"))
            documents = manifest.get("documents", []) if isinstance(manifest, dict) else []
            artifacts = manifest.get("artifacts", []) if isinstance(manifest, dict) else []
            if not isinstance(documents, list) or not documents or not isinstance(artifacts, list):
                raise ValueError("El run detailed-analysis no contiene artefactos")
            requested = job.options.get("generation", {}).get("artifacts", [])
            generated = {item.get("id") for item in artifacts if isinstance(item, dict)}
            if requested and not set(requested).issubset(generated):
                raise ValueError("El run detailed-analysis no contiene todos los artefactos solicitados")
            for item in documents:
                path = Path(str(item))
                path = path if path.is_absolute() else run_dir / path
                if not path.is_file() and Path(str(item)).is_absolute():
                    path = output / Path(str(item)).name
                if not path.is_file():
                    raise ValueError("El run detailed-analysis contiene un artefacto ausente")
