from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from litman_core.domain.jobs import PublishedArtifact
from .common import CatalogArtifact, sha256


class LocalDocumentSource:
    def materialize(self, job, workspace: Path):
        from litman_core.domain.jobs import MaterializedCase
        source = Path(job.input_location).expanduser().resolve()
        if not source.is_dir(): raise ValueError(f"No existe el directorio de entrada: {source}")
        target = workspace / "case"; shutil.copytree(source, target)
        return MaterializedCase(job.job_id, target)


class LocalArtifactPublisher:
    """Reduce the already allocated canonical run only after all remote work."""
    def publish(self, run_dir: Path, inventory: tuple[CatalogArtifact, ...], *, include_run_files: bool) -> tuple[PublishedArtifact, ...]:
        if not include_run_files:
            temporary = run_dir.with_name(f".{run_dir.name}.catalog-{uuid.uuid4().hex}")
            backup = run_dir.with_name(f".{run_dir.name}.complete-{uuid.uuid4().hex}")
            try:
                temporary.mkdir()
                for item in inventory:
                    destination = temporary / item.relative_path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item.source, destination)
                    if sha256(destination) != item.checksum: raise RuntimeError("El hash del catálogo local no coincide")
                os.rename(run_dir, backup)
                try:
                    os.rename(temporary, run_dir)
                except Exception:
                    os.rename(backup, run_dir)
                    raise
                try:
                    shutil.rmtree(backup)
                except Exception:
                    # A successful rename is not enough: retain the complete
                    # diagnostic run if removing its backup cannot be proven.
                    os.rename(run_dir, temporary)
                    os.rename(backup, run_dir)
                    raise
            except Exception:
                shutil.rmtree(temporary, ignore_errors=True)
                raise
        return tuple(PublishedArtifact(item.relative_path, (run_dir / item.relative_path).as_uri(), item.checksum) for item in inventory)
