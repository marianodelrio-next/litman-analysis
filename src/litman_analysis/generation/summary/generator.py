from __future__ import annotations

import json
from pathlib import Path

from .renderer import write_summary
from ..models import ArtifactContext


class SummaryGenerator:
    id = "summary"
    version = "summary-generator-v1"

    def generate(self, context: ArtifactContext) -> dict:
        output = context.run_dir / "output" / "resumen.docx"
        write_summary(context.dossier, output)
        return self._result(output)

    def rerender(self, run_dir: Path, **options: object) -> dict:
        dossier = json.loads((run_dir / "input" / "dossier.json").read_text(encoding="utf-8"))
        output = run_dir / "output" / "resumen.docx"
        write_summary(dossier, output)
        return self._result(output)

    def _result(self, output: Path) -> dict:
        return {"id": self.id, "generator_version": self.version, "documents": [str(output)],
                "validation": {"valid": True}, "pending": [], "metadata": {"format": "docx"}}
