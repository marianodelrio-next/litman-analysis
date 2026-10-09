from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Callable

from litman_core.domain.jobs import JobRequest, MaterializedCase, PublishedArtifact
from .common import manifest, publication_catalog, write_manifest
from .publication import publication_folder_name


class LocalDocumentSource:
    def materialize(self, job: JobRequest, workspace: Path) -> MaterializedCase:
        source = Path(job.input_location).expanduser().resolve()
        if not source.is_dir():
            raise ValueError(f"No existe el directorio de entrada: {source}")
        target = workspace / "case"
        shutil.copytree(source, target)
        return MaterializedCase(job.job_id, target)


class LocalArtifactPublisher:
    def __init__(self, temporary_suffix: Callable[[], str] | None = None,
                 publication_name_factory: Callable[[str], str] = publication_folder_name) -> None:
        self._temporary_suffix = temporary_suffix or (lambda: uuid.uuid4().hex)
        self._publication_name_factory = publication_name_factory

    def publish(self, job: JobRequest, run_dir: Path) -> tuple[PublishedArtifact, ...]:
        root = Path(job.output_location).expanduser().resolve()
        publication_id = self._publication_name_factory(job.job_id)
        target = root / publication_id
        catalog = publication_catalog(run_dir)
        if target.exists():
            raise FileExistsError(f"La carpeta de publicación ya existe: {target}")
        root.mkdir(parents=True, exist_ok=True)
        temporary = root / f".{publication_id}.tmp-{self._temporary_suffix()}"
        try:
            temporary.mkdir()
            artifacts = []
            for item in catalog:
                destination = temporary / item.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item.source, destination)
                artifacts.append((item.name, item.checksum, (target / item.name).as_uri()))
            write_manifest(temporary / "publication-manifest.json", manifest(job.job_id, publication_id, job.job_type, artifacts))
            if target.exists():
                shutil.rmtree(temporary, ignore_errors=True)
                raise FileExistsError(f"La carpeta de publicación ya existe: {target}")
            os.rename(temporary, target)
            return tuple(PublishedArtifact(name, uri, checksum) for name, checksum, uri in artifacts)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
