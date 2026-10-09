from __future__ import annotations

from pathlib import Path
from typing import Protocol

from litman_core.domain.jobs import JobRequest, MaterializedCase


class DocumentSource(Protocol):
    """Descarga o copia los documentos de un job a un workspace aislado."""

    def materialize(self, job: JobRequest, workspace: Path) -> MaterializedCase:
        ...

