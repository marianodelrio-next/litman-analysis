from __future__ import annotations

from pathlib import Path

from .extraction import prepare_assessment, run_assessment
from litman_core.infrastructure.documents.bundle import DocumentBundle
from litman_core.config import Settings
from litman_core.application.ports.llm import LLMProvider


class AssessmentPipeline:
    """Caso de uso del análisis inicial."""

    def __init__(self, settings: Settings, provider: LLMProvider) -> None:
        self.settings = settings
        self.provider = provider

    def execute(self, case_dir: Path, *, run_dir: Path,
                bundle: DocumentBundle | None = None) -> tuple[Path, dict]:
        prepared = prepare_assessment(case_dir, self.settings, run_dir=run_dir, bundle=bundle)
        return prepared.run_dir, run_assessment(prepared, self.provider)
