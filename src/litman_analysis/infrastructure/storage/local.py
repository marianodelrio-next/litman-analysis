from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Callable

from litman_analysis.domain.jobs import JobRequest, MaterializedCase, PublishedArtifact
from .common import compatible_manifest, manifest, publication_catalog, sha256, write_manifest


class LocalDocumentSource:
    def materialize(self, job: JobRequest, workspace: Path) -> MaterializedCase:
        source = Path(job.input_location).expanduser().resolve()
        if not source.is_dir():
            raise ValueError(f"No existe el directorio de entrada: {source}")
        target = workspace / "case"
        shutil.copytree(source, target)
        return MaterializedCase(job.job_id, target)


class LocalArtifactPublisher:
    def __init__(self, temporary_suffix: Callable[[], str] | None = None) -> None:
        self._temporary_suffix = temporary_suffix or (lambda: uuid.uuid4().hex)

    def publish(self, job: JobRequest, run_dir: Path) -> tuple[PublishedArtifact, ...]:
        root = Path(job.output_location).expanduser().resolve()
        target = root / job.job_id
        catalog = publication_catalog(run_dir)
        if target.exists():
            return self._existing(target, job, catalog)
        root.mkdir(parents=True, exist_ok=True)
        temporary = root / f".{job.job_id}.tmp-{self._temporary_suffix()}"
        try:
            temporary.mkdir()
            artifacts = []
            for item in catalog:
                destination = temporary / item.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item.source, destination)
                artifacts.append((item.name, item.checksum, (target / item.name).as_uri()))
            write_manifest(temporary / "publication-manifest.json", manifest(job.job_id, job.job_type, artifacts))
            if target.exists():
                existing = self._existing(target, job, catalog)
                shutil.rmtree(temporary, ignore_errors=True)
                return existing
            os.rename(temporary, target)
            return tuple(PublishedArtifact(name, uri, checksum) for name, checksum, uri in artifacts)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise

    def _existing(self, target: Path, job: JobRequest, catalog: tuple) -> tuple[PublishedArtifact, ...]:
        try:
            value = json.loads((target / "publication-manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FileExistsError(f"La salida del job ya existe sin un manifest válido: {target}") from exc
        if not compatible_manifest(value, job.job_id, job.job_type, catalog):
            raise FileExistsError(f"La salida del job ya existe con contenido diferente: {target}")
        return tuple(PublishedArtifact(item["name"], item["uri"], item["sha256"]) for item in value["artifacts"])
