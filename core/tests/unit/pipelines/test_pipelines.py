from __future__ import annotations

import ast
import importlib
import inspect
import json
import pkgutil
import shutil
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from litman_core.application.ports.llm import LLMResult
from litman_core.config import Settings
from litman_core.pipelines.assessment.extraction import prepare_assessment, run_assessment
from litman_core.pipelines.assessment.stage import definition as assessment_definition
from litman_core.pipelines.detailed_analysis.extraction import (
    prepare_detailed_analysis,
    run_detailed_analysis,
)
from litman_core.pipelines.detailed_analysis.stage import definition as detailed_analysis_definition
from litman_core.pipelines.models import StageDefinition, StageOutcome, StagePreparation, StageResources
from litman_core.pipelines.runner import prepare_stage, run_stage
from litman_core.resource_paths import RESOURCE_ROOT
class FakeProvider:
    def generate(self, **_kwargs):
        return LLMResult(
            {"answer": "ok"}, "fake", "test-model", "response-1",
            {"tokens": 3}, {"seconds": 1},
        )


def test_versioned_prompts_require_spanish_semantics_and_verbatim_sources() -> None:
    assessment = (RESOURCE_ROOT / "pipelines/assessment/v1/system.md").read_text(encoding="utf-8")
    detailed = (RESOURCE_ROOT / "pipelines/detailed/v1/system.md").read_text(encoding="utf-8")
    detailed_task = (RESOURCE_ROOT / "pipelines/detailed/v1/extraction.md").read_text(encoding="utf-8")
    generation_system = (RESOURCE_ROOT / "pipelines/detailed/v1/generation/system.md").read_text(encoding="utf-8")
    generation_task = (RESOURCE_ROOT / "pipelines/detailed/v1/generation/generation.md").read_text(encoding="utf-8")
    assert "campos semánticos y narrativos, aunque la fuente" in assessment
    assert "texto_citado" in assessment
    for literal in ("texto_citado", "expresion_literal", "formula_literal"):
        assert literal in detailed
    assert "identificadores, niveles y número" in generation_system
    assert "títulos del pliego para su presentación" in generation_system
    for literal in ("nombres propios", "nombres de documentos", "nombres de archivo",
                    "referencias\n  estables", "página o sección", "fórmulas literales"):
        assert literal in generation_system
    assert "mismo id y\nnivel" in generation_task
    assert "obligatorio redactar en español todo contenido" in generation_task
    assert "estructura_documento_tecnico" in detailed_task
    assert "subapartados[].titulo" in detailed_task
    assert "traduce al español sus rótulos ordinarios" in detailed_task
    assert (RESOURCE_ROOT / "pipelines/assessment/v1/VERSION").read_text().strip() == "assessment-prompt-v3"
    assert (RESOURCE_ROOT / "pipelines/detailed/v1/VERSION").read_text().strip() == "detailed-analysis-prompt-v4"
    assert (RESOURCE_ROOT / "pipelines/detailed/v1/generation/VERSION").read_text().strip() == "detailed-generation-prompt-v5"


def test_stage_can_prepare_versioned_resources_and_persists_common_files(tmp_path: Path) -> None:
    project = tmp_path / "project"
    resources = project / "resources"
    resources.mkdir(parents=True)
    (resources / "system.md").write_text("system")
    (resources / "extraction.md").write_text("task")
    (resources / "VERSION").write_text("v-test")
    config = project / "config.yaml"
    config.write_text("version: config-test\n")
    schema = project / "schema.json"
    schema.write_text('{"$id": "schema-test"}')
    case = tmp_path / "case"
    case.mkdir()
    (case / "source.txt").write_text("contenido")
    settings = Settings()

    definition = StageDefinition(
        identifier="test-stage",
        version="2026.1",
        resources=lambda _settings: StageResources(resources, config, schema),
        prepare_prompt=lambda loaded, _docs, _normalized, _context: StagePreparation(
            f"{loaded.task} prepared"
        ),
        request_metadata=lambda *_args: {"stage_version": "2026.1"},
        validate=lambda _data, _prepared: {
            "valid": True, "schema_errors": [], "evidence_errors": [],
        },
        build_outcome=lambda response, validation, _prepared: StageOutcome(
            {"payload": response.data, "validation": validation},
            {"payload.json": response.data},
            {"valid": validation["valid"], "error_count": 0},
        ),
    )

    prepared = prepare_stage(definition, case, settings, run_dir=tmp_path / "run")
    request = json.loads((prepared.run_dir / "input" / "request.json").read_text())
    assert request == {
        "provider": "codex",
        "model": "gpt-5.6-luna",
        "prompt_version": "v-test",
        "config_version": "config-test",
        "schema_id": "schema-test",
        "stage_version": "2026.1",
    }
    result = run_stage(definition, prepared, FakeProvider())
    assert result["payload"] == {"answer": "ok"}
    for path in (
        "input/manifest.json", "input/prompt.md", "input/request.json",
        "output/payload.json", "output/metrics.json", "output/result.json",
    ):
        assert (prepared.run_dir / path).is_file()


def test_pipeline_definitions_keep_their_domain_hooks_and_facades() -> None:
    assessment = assessment_definition()
    detailed = detailed_analysis_definition()
    assert (assessment.identifier, assessment.version) == ("assessment", "1")
    assert (detailed.identifier, detailed.version) == ("detailed-analysis", "1")
    assert assessment.prepare_prompt is not detailed.prepare_prompt
    assert assessment.build_outcome is not detailed.build_outcome
    assert assessment.postprocess is not None
    assert detailed.postprocess is not None
    assert "evidence-index.json" in assessment.output_files
    assert "dossier.json" in detailed.output_files
    assert list(inspect.signature(prepare_assessment).parameters) == [
        "case_dir", "settings", "run_dir", "bundle",
    ]
    assert list(inspect.signature(prepare_detailed_analysis).parameters) == [
        "case_dir", "settings", "run_dir", "bundle", "assessment_result",
    ]
    assert list(inspect.signature(run_assessment).parameters) == ["prepared", "provider"]
    assert list(inspect.signature(run_detailed_analysis).parameters) == ["prepared", "provider"]


@pytest.mark.parametrize("module_name", [
    "litman_core.pipelines.assessment.stage",
    "litman_core.pipelines.detailed_analysis.stage",
])
def test_unverified_quotes_are_warnings_not_fatal(module_name, monkeypatch) -> None:
    module = importlib.import_module(module_name)
    monkeypatch.setattr(module, "validate_extraction", lambda *_args, **_kwargs: {
        "valid": True, "schema_errors": [], "evidence_errors": [], "semantic_errors": [],
    })
    monkeypatch.setattr(module, "build_evidence_index", lambda *_args: {"evidences": []})
    monkeypatch.setattr(module, "verification_errors", lambda _index: [
        {"path":"field", "message":"quote_not_found", "evidence_id":"ev_x"},
    ])
    prepared = SimpleNamespace(
        resources=SimpleNamespace(schema={}), documents=[], normalized=[], context={})
    validation = module._validate({}, prepared)
    assert validation["valid"] is True
    assert validation["complete"] is False
    assert validation["warnings"] == [{"kind":"unverified_evidence", "count":1}]


def test_registered_pipelines_resolve_and_expose_version_bundles() -> None:
    from litman_core.pipelines.registry import PIPELINES

    assessment = PIPELINES.get("assessment").resolve(RESOURCE_ROOT)
    detailed = PIPELINES.get("detailed-analysis").resolve(RESOURCE_ROOT)
    assert assessment.version_bundle()["pipeline_id"] == "assessment"
    assert assessment.version_bundle()["versions"]["rules"] == "assessment-rules-v2"
    assert detailed.version_bundle()["pipeline_id"] == "detailed-analysis"
    assert "rules" not in detailed.version_bundle()["versions"]
    assert assessment.version_bundle()["sha256"] == assessment.version_bundle()["sha256"]


def test_incomplete_pipeline_definition_fails_with_clear_error(tmp_path: Path) -> None:
    from litman_core.pipelines.registry import PipelineDefinition

    definition = PipelineDefinition(
        "broken", "1", Path("missing-system.md"), Path("missing-task.md"),
        Path("VERSION"), Path("schema.json"), Path("config.yaml"),
    )
    with pytest.raises(ValueError, match="Definición de pipeline incompleta"):
        definition.resolve(tmp_path)


def test_prepare_assessment_persists_version_bundle(tmp_path: Path) -> None:
    project = tmp_path / "project"
    for relative in ("pipelines/assessment/v1", "schemas/assessment.schema.json"):
        source = RESOURCE_ROOT / relative
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    case = tmp_path / "case"
    case.mkdir()
    (case / "source.txt").write_text("contenido", encoding="utf-8")

    prepared = prepare_assessment(
        case, Settings(resource_root=project), run_dir=tmp_path / "run"
    )
    request = json.loads(
        (prepared.run_dir / "input" / "request.json").read_text(encoding="utf-8")
    )
    bundle = request["version_bundle"]
    assert bundle["pipeline_id"] == "assessment"
    assert bundle["versions"]["schema_id"] == request["schema_id"]
    assert len(bundle["sha256"]["schema"]) == 64


def test_prompt_paths_point_to_agent_workspace_when_paths_have_backslashes(tmp_path: Path) -> None:
    # Windows paths contain backslashes, which the JSON prompt escapes.
    case = tmp_path / "case"
    case.mkdir()
    (case / "source.txt").write_text("contenido", encoding="utf-8")

    prepared = prepare_assessment(case, Settings(), run_dir=tmp_path / "C:\\runs\\run")

    ready = [item for item in prepared.normalized if item.status == "ready"]
    assert ready
    for item in ready:
        workspace_path = Path(item.normalized_path)
        assert workspace_path.parent.parent.name == "agent-workspace"
        original_path = prepared.run_dir / "input" / "documents" / workspace_path.name
        assert json.dumps(str(workspace_path))[1:-1] in prepared.prompt
        assert json.dumps(str(original_path))[1:-1] not in prepared.prompt


@pytest.mark.parametrize("command", ["assess", "analyze", "check"])
def test_removed_public_commands_are_rejected(monkeypatch, command: str) -> None:
    from litman_core.cli import main

    monkeypatch.setattr("sys.argv", ["litman-core", command, "--help"])
    with pytest.raises(SystemExit) as exit_status:
        main()
    assert exit_status.value.code == 2


def test_public_modules_and_composition_roots_import() -> None:
    modules = (
        "litman_core.cli",
        "litman_core.infrastructure.runs",
        "litman_core.infrastructure.documents.bundle",
        "litman_core.infrastructure.llm.codex_cli",
        "litman_core.domain.validation",
        "litman_core.pipelines.registry",
        "litman_core.pipelines.runner",
        "litman_core.generation",
        "litman_core.generation.opportunity_report",
        "litman_core.pipelines",
    )
    assert all(importlib.import_module(name) for name in modules)


def test_all_litman_core_modules_import() -> None:
    import litman_core

    modules = [name for _, name, _ in pkgutil.walk_packages(litman_core.__path__, "litman_core.")]
    assert all(importlib.import_module(name) for name in modules)


def test_registries_declare_all_runtime_components() -> None:
    from litman_core.generation import ARTIFACT_GENERATORS
    from litman_core.pipelines.registry import PIPELINES

    assert {PIPELINES.get(name).identifier for name in ("assessment", "detailed-analysis")} == {
        "assessment", "detailed-analysis",
    }
    assert set(ARTIFACT_GENERATORS) == {
        "technical-summary", "bid-preparation-guide", "technical-document", "economic-simulator",
    }


def test_detailed_analysis_has_no_dependency_on_assessment_implementation() -> None:
    source = Path(__file__).parents[3] / "src" / "litman_core" / "pipelines" / "detailed_analysis"
    paths = list(source.glob("*.py"))
    assert paths, source
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = [
            node.module or "" for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        ]
        assert not any(name.startswith("litman_core.pipelines.assessment") for name in imports), path


def test_failed_stage_persists_validation_diagnostics_before_raising(tmp_path: Path) -> None:
    resources = tmp_path / "resources"
    resources.mkdir()
    for name, content in (("system.md", "system"), ("extraction.md", "task"), ("VERSION", "v")):
        (resources / name).write_text(content, encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text("version: v\n", encoding="utf-8")
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")
    case = tmp_path / "case"
    case.mkdir()
    (case / "doc.md").write_text("contenido", encoding="utf-8")
    definition = StageDefinition(
        identifier="invalid", version="1",
        resources=lambda _settings: StageResources(resources, config, schema),
        prepare_prompt=lambda loaded, *_args: StagePreparation(loaded.task),
        request_metadata=lambda *_args: {},
        validate=lambda *_args: {"valid": False, "schema_errors": ["canary"]},
        build_outcome=lambda *_args: pytest.fail("no debe construir output"),
    )
    prepared = prepare_stage(definition, case, Settings(), run_dir=tmp_path / "run")
    with pytest.raises(ValueError, match="validación"):
        run_stage(definition, prepared, FakeProvider())
    assert json.loads((prepared.run_dir / "output" / "validation.json").read_text(encoding="utf-8"))["schema_errors"] == ["canary"]
def test_resolved_toml_model_is_used_for_stage_metadata():
    # Simulates JobRunner's replace() after resolve_llm(job) picked the TOML selection.
    settings = replace(Settings(), llm_provider="claude-code", llm_model="sonnet")
    from litman_core.pipelines.detailed_analysis.stage import _request_metadata
    assert _request_metadata(settings, None, None, {}) == {"model": "sonnet"}
