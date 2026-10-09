from __future__ import annotations

from pathlib import Path
from typing import Any

from .extraction import prepare_detailed_analysis, run_detailed_analysis
from litman_core.config import Settings
from litman_core.generation.service import generate_documents
from litman_core.application.ports.llm import LLMProvider
from litman_core.infrastructure.documents.bundle import DocumentBundle


class DetailedAnalysisPipeline:
    """Une extracción detallada y generación sin ocultar sus fases reintentables."""

    def __init__(self, settings: Settings, provider: LLMProvider) -> None:
        self.settings = settings
        self.provider = provider

    def execute(self, case_dir: Path, *, case_id: str | None = None,
                assessment_result: dict | None = None,
                generation: dict[str, Any] | None = None,
                bundle: DocumentBundle | None = None) -> tuple[Path, dict]:
        generation = generation or {}
        prepared = prepare_detailed_analysis(
            case_dir, self.settings, assessment_result=assessment_result,
            run_case_id=case_id, bundle=bundle,
        )
        extraction = run_detailed_analysis(prepared, self.provider)
        dossier = prepared.run_dir / "output" / "dossier.json"
        technical = generation.get("technical_document", {})
        economic = generation.get("economic_simulator", {})
        artifacts = generate_documents(
            dossier, output_dir=prepared.run_dir,
            artifacts=generation.get("artifacts"), provider=self.provider,
            template_id=technical.get("template_id", "next-standard-v1"),
            economic_template_id=economic.get("template_id", "standard-v1"),
            include_internal_pending=technical.get("include_internal_pending", True),
            include_editorial_guidance=technical.get("include_editorial_guidance", True),
            output_language=technical.get("output_language", "auto"),
            content_profile=technical.get("content_profile", "skeleton-v1"),
        )
        return prepared.run_dir, {"extraction": extraction, "generation": artifacts}
