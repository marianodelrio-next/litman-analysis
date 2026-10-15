from __future__ import annotations

from pathlib import Path

from ..models import ArtifactContext
from .renderer import write_bid_preparation_guide


class BidPreparationGuideGenerator:
    """Operational bid-preparation guide."""
    id = "bid-preparation-guide"
    version = "bid-preparation-guide-generator-v4"
    filename = "guia_preparacion_oferta.docx"

    def generate(self, context: ArtifactContext) -> dict:
        output = context.run_dir / "output" / self.filename
        write_bid_preparation_guide(context.dossier, output)
        return self._result(output, context.dossier)

    def _result(self, output: Path, dossier: dict) -> dict:
        pending = dossier.get("pendientes") if isinstance(dossier.get("pendientes"), list) else []
        return {"id": self.id, "generator_version": self.version, "documents": [str(output)],
                "validation": {"valid": True}, "pending": pending, "metadata": {"format": "docx"}}

