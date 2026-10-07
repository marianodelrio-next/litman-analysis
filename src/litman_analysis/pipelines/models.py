from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from litman_analysis.domain.documents import Document, NormalizedDocument
from litman_analysis.application.ports.llm import LLMResult


@dataclass(frozen=True)
class StageResources:
    """Recursos versionados que una etapa necesita para ejecutarse."""

    prompt_dir: Path
    config_path: Path
    schema_path: Path
    rules_path: Path | None = None
    version_bundle: dict[str, Any] | None = None
    system_prompt_path: Path | None = None
    task_prompt_path: Path | None = None
    prompt_version_path: Path | None = None


@dataclass(frozen=True)
class LoadedResources:
    instructions: str
    task: str
    prompt_version: str
    config: dict[str, Any]
    schema: dict[str, Any]
    rules_path: Path | None = None
    version_bundle: dict[str, Any] | None = None


@dataclass(frozen=True)
class StageFiles:
    """Nombres de los artefactos comunes de una etapa."""

    manifest: str = "manifest.json"
    prompt: str = "prompt.md"
    request: str = "request.json"
    result: str = "result.json"
    metrics: str = "metrics.json"


@dataclass
class StagePreparation:
    prompt: str
    context: dict[str, Any] = field(default_factory=dict)
    input_artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass
class PreparedStage:
    case_dir: Path
    run_dir: Path
    documents: list[Document]
    normalized: list[NormalizedDocument]
    resources: LoadedResources
    schema_path: Path
    prompt: str
    context: dict[str, Any]


@dataclass
class StageOutcome:
    result: dict[str, Any]
    output_artifacts: dict[str, Any]
    metrics_validation: dict[str, Any]


@dataclass(frozen=True)
class StageDefinition:
    """Declaración de una etapa; los callbacks contienen sólo lógica de dominio."""

    identifier: str
    version: str
    resources: Callable[[Any], StageResources]
    prepare_prompt: Callable[[LoadedResources, list[Document], list[NormalizedDocument], dict[str, Any]], StagePreparation]
    request_metadata: Callable[[Any, LoadedResources, list[NormalizedDocument], dict[str, Any]], dict[str, Any]]
    validate: Callable[[dict[str, Any], PreparedStage], dict[str, Any]]
    build_outcome: Callable[[LLMResult, dict[str, Any], PreparedStage], StageOutcome]
    postprocess: Callable[[StageOutcome, PreparedStage], None] | None = None
    files: StageFiles = StageFiles()
    output_files: tuple[str, ...] = ()
