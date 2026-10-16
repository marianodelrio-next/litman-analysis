"""Registro explícito de los recursos que forman cada pipeline.

No se infieren rutas a partir del identificador: cada alta declara todos sus
recursos, de modo que un error se detecta al resolverla, antes de crear un run.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Mapping

import yaml


@dataclass(frozen=True)
class PipelineDefinition:
    identifier: str
    functional_version: str
    system_prompt: Path
    task_prompt: Path
    prompt_version: Path
    schema: Path
    config: Path
    rules: Path | None = None
    hooks: Mapping[str, str] | None = None

    def resolve(self, project_root: Path) -> "ResolvedPipelineDefinition":
        paths = {
            "system_prompt": project_root / self.system_prompt,
            "task_prompt": project_root / self.task_prompt,
            "prompt_version": project_root / self.prompt_version,
            "schema": project_root / self.schema,
            "config": project_root / self.config,
        }
        if self.rules is not None:
            paths["rules"] = project_root / self.rules
        missing = [name for name, path in paths.items() if not path.is_file()]
        if missing:
            details = ", ".join(f"{name} ({paths[name]})" for name in missing)
            raise ValueError(f"Definición de pipeline incompleta para '{self.identifier}': falta {details}")
        try:
            config = yaml.safe_load(paths["config"].read_text(encoding="utf-8"))
            schema = json.loads(paths["schema"].read_text(encoding="utf-8"))
        except (json.JSONDecodeError, yaml.YAMLError) as exc:
            raise ValueError(f"Definición de pipeline inválida para '{self.identifier}': {exc}") from exc
        if not isinstance(config, dict) or not isinstance(config.get("version"), str):
            raise ValueError(f"Definición de pipeline inválida para '{self.identifier}': config sin version")
        if not isinstance(schema, dict) or not isinstance(schema.get("$id"), str):
            raise ValueError(f"Definición de pipeline inválida para '{self.identifier}': schema sin $id")
        if not paths["prompt_version"].read_text(encoding="utf-8").strip():
            raise ValueError(f"Definición de pipeline inválida para '{self.identifier}': VERSION vacío")
        return ResolvedPipelineDefinition(self, paths, config, schema)


@dataclass(frozen=True)
class ResolvedPipelineDefinition:
    definition: PipelineDefinition
    paths: Mapping[str, Path]
    config: dict
    schema: dict

    def version_bundle(self) -> dict:
        """Información inmutable suficiente para reproducir o auditar un run."""
        versions = {
            "pipeline": self.definition.functional_version,
            "prompt": self.paths["prompt_version"].read_text(encoding="utf-8").strip(),
            "schema_id": self.schema["$id"],
            "config": self.config["version"],
        }
        if "rules" in self.paths:
            rules = yaml.safe_load(self.paths["rules"].read_text(encoding="utf-8"))
            if not isinstance(rules, dict) or not isinstance(rules.get("version"), str):
                raise ValueError(f"Definición de pipeline inválida para '{self.definition.identifier}': reglas sin version")
            versions["rules"] = rules["version"]
        return {
            "pipeline_id": self.definition.identifier,
            "versions": versions,
            "sha256": {name: sha256(path.read_bytes()).hexdigest() for name, path in self.paths.items()},
        }


class PipelineRegistry:
    def __init__(self, definitions: tuple[PipelineDefinition, ...]):
        self._definitions = {definition.identifier: definition for definition in definitions}
        if len(self._definitions) != len(definitions):
            raise ValueError("El registro de pipelines contiene identificadores duplicados")

    def get(self, identifier: str) -> PipelineDefinition:
        try:
            return self._definitions[identifier]
        except KeyError as exc:
            raise KeyError(f"Pipeline no registrado: {identifier}") from exc


PIPELINES = PipelineRegistry((
    PipelineDefinition(
        identifier="assessment", functional_version="1",
        system_prompt=Path("pipelines/assessment/v1/system.md"), task_prompt=Path("pipelines/assessment/v1/extraction.md"),
        prompt_version=Path("pipelines/assessment/v1/VERSION"), schema=Path("schemas/assessment.schema.json"),
        config=Path("pipelines/assessment/v1/config.yaml"), rules=Path("pipelines/assessment/v1/rules.yaml"),
        hooks={"stage": "litman_core.pipelines.assessment.stage.definition"},
    ),
    PipelineDefinition(
        identifier="detailed-analysis", functional_version="1",
        system_prompt=Path("pipelines/detailed/v1/system.md"), task_prompt=Path("pipelines/detailed/v1/extraction.md"),
        prompt_version=Path("pipelines/detailed/v1/VERSION"), schema=Path("schemas/detailed-analysis.schema.json"),
        config=Path("pipelines/detailed/v1/config.yaml"),
        hooks={"stage": "litman_core.pipelines.detailed_analysis.stage.definition"},
    ),
))
