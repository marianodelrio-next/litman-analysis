from __future__ import annotations

from pathlib import Path
from typing import Protocol

from litman_analysis.domain.jobs import JobRequest, PublishedArtifact


class ArtifactPublisher(Protocol):
    """Publica los resultados duraderos producidos por una ejecución."""

    def publish(self, job: JobRequest, run_dir: Path) -> tuple[PublishedArtifact, ...]:
        ...

