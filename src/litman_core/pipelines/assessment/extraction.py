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
class AssessmentPreparation:
    """Datos preparados para ejecutar el análisis inicial."""
    stage: PreparedStage

    @property
    def case_dir(self): return self.stage.case_dir
    @property
    def run_dir(self): return self.stage.run_dir
    @property
    def documents(self): return self.stage.documents
    @property
    def normalized(self): return self.stage.normalized
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
    def rules(self): return self.stage.context["rules"]


def prepare_assessment(case_dir: Path, settings: Settings | None = None,
                     bundle: DocumentBundle | None = None,
                     run_case_id: str | None = None) -> AssessmentPreparation:
    settings = settings or Settings()
    return AssessmentPreparation(prepare_stage(definition(), case_dir, settings, bundle=bundle,
                                          context={"settings": settings}, run_case_id=run_case_id))


def run_assessment(prepared: AssessmentPreparation, provider: LLMProvider) -> dict:
    return run_stage(definition(), prepared.stage, provider)
