from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from litman_core.config import Settings
from litman_core.infrastructure.documents.bundle import DocumentBundle
from litman_core.application.ports.llm import LLMProvider
from .stage import definition
from litman_core.pipelines.models import PreparedStage
from litman_core.pipelines.runner import prepare_stage, run_stage


@dataclass
class DetailedAnalysisPreparation:
    """Datos preparados para ejecutar el análisis detallado."""

    stage: PreparedStage

    @property
    def case_dir(self): return self.stage.case_dir
    @property
    def run_dir(self): return self.stage.run_dir
    @property
    def documents(self): return self.stage.documents
    @property
    def instructions(self): return self.stage.resources.instructions
    @property
    def prompt(self): return self.stage.prompt
    @property
    def prompt_version(self): return self.stage.resources.prompt_version
    @property
    def schema_path(self): return self.stage.schema_path
    @property
    def schema(self): return self.stage.resources.schema
    @property
    def config_version(self): return self.stage.resources.config["version"]


def prepare_detailed_analysis(case_dir: Path, settings: Settings | None = None,
                     bundle: DocumentBundle | None = None,
                     assessment_result: dict | None = None,
                     run_case_id: str | None = None, run_dir: Path | None = None) -> DetailedAnalysisPreparation:
    settings = settings or Settings()
    return DetailedAnalysisPreparation(prepare_stage(definition(), case_dir, settings, bundle=bundle,
                                           context={"assessment_result": assessment_result}, run_case_id=run_case_id, run_dir=run_dir))


def run_detailed_analysis(prepared: DetailedAnalysisPreparation, provider: LLMProvider) -> dict:
    return run_stage(definition(), prepared.stage, provider)
