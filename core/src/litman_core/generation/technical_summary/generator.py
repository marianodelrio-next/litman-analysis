from __future__ import annotations

from pathlib import Path

from ..models import ArtifactContext
from .renderer import write_technical_summary


class TechnicalSummaryGenerator:
    id = "technical-summary"
    version = "technical-summary-generator-v3"
    filename = "resumen_tecnico.docx"

    def generate(self, context: ArtifactContext) -> dict:
        output = context.run_dir / "output" / self.filename
        write_technical_summary(context.dossier, output)
        return self._result(output)

    def _result(self, output: Path) -> dict:
        return {"id": self.id, "generator_version": self.version, "documents": [str(output)],
                "validation": {"valid": True}, "pending": [], "metadata": {"format": "docx"}}

