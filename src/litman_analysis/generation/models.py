from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from litman_analysis.application.ports.llm import LLMProvider


@dataclass(frozen=True)
class ArtifactContext:
    dossier: dict
    run_dir: Path
    source_run: Path | None
    case_dir: Path
    template_id: str
    economic_template_id: str
    include_internal_pending: bool
    output_language: str
    content_profile: str
    provider: LLMProvider | None
    include_editorial_guidance: bool = True


class ArtifactGenerator(Protocol):
    id: str
    version: str

    def generate(self, context: ArtifactContext) -> dict: ...
    def rerender(self, run_dir: Path, **options: object) -> dict: ...
