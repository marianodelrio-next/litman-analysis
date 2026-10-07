from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from dataclasses import replace
from typing import Any

import yaml

from litman_analysis.infrastructure.documents.bundle import DocumentBundle
from litman_analysis.infrastructure.documents.inventory import inventory
from litman_analysis.infrastructure.documents.normalize import normalize_documents
from litman_analysis.application.ports.llm import LLMProvider, output_paths_for_run
from litman_analysis.infrastructure.runs import new_run_dir

from .models import LoadedResources, PreparedStage, StageDefinition


def prepare_stage(definition: StageDefinition, case_dir: Path, settings: Any, *,
                  bundle: DocumentBundle | None = None, context: dict[str, Any] | None = None,
                  run_case_id: str | None = None) -> PreparedStage:
    case_dir = case_dir.resolve()
    documents = bundle.documents if bundle else inventory(case_dir, settings.max_file_mb)
    print(f"[{definition.identifier} inventario] {len(documents)} documentos detectados", file=sys.stderr, flush=True)
    if not documents:
        raise ValueError(f"El caso no contiene documentos: {case_dir}")
    resource_paths = definition.resources(settings)
    loaded = _load_resources(resource_paths.system_prompt_path or resource_paths.prompt_dir / "system.md",
                             resource_paths.task_prompt_path or resource_paths.prompt_dir / "extraction.md",
                             resource_paths.prompt_version_path or resource_paths.prompt_dir / "VERSION",
                             resource_paths.config_path, resource_paths.schema_path, resource_paths.rules_path,
                             resource_paths.version_bundle)
    run_dir = new_run_dir(settings.runs_dir, case_dir, definition.identifier, case_name=run_case_id)
    normalized = bundle.normalized if bundle else normalize_documents(documents, run_dir / "input" / "documents")
    preparation = definition.prepare_prompt(loaded, documents, normalized, context or {})
    prepared = PreparedStage(case_dir, run_dir, documents, normalized, loaded, resource_paths.schema_path,
                             preparation.prompt, preparation.context)
    prepared = _build_agent_workspace(prepared, settings)
    _write_json(run_dir / "input" / definition.files.manifest, {
        "case_dir": str(case_dir), "documents": [doc.public_dict() for doc in documents],
        "normalized_documents": [doc.public_dict() for doc in normalized],
    })
    for name, value in preparation.input_artifacts.items():
        _write_json(run_dir / "input" / name, value)
    (run_dir / "input" / definition.files.prompt).write_text(
        f"{loaded.instructions}\n\n---\n\n{preparation.prompt}", encoding="utf-8"
    )
    request = {"provider": "codex_cli", "model": settings.codex_model or "codex_default",
               "prompt_version": loaded.prompt_version, "config_version": loaded.config["version"],
               "schema_id": loaded.schema.get("$id")}
    if loaded.version_bundle is not None:
        request["version_bundle"] = loaded.version_bundle
    request.update(definition.request_metadata(settings, loaded, normalized, preparation.context))
    _write_json(run_dir / "input" / definition.files.request, request)
    print(f"[{definition.identifier} preparación] ejecución lista: {run_dir}", file=sys.stderr, flush=True)
    return prepared


def _build_agent_workspace(prepared: PreparedStage, settings: Any) -> PreparedStage:
    """Create the document tree supplied as Codex working directory.

    Every run uses a private, read-only document copy below its persistent run.
    """
    workspace = prepared.run_dir / "agent-workspace"
    documents_dir = workspace / "documents"
    documents_dir.mkdir(parents=True, exist_ok=True)
    remapped = []
    prompt = prepared.prompt
    for item in prepared.normalized:
        if item.status == "ready" and item.normalized_path:
            source = Path(item.normalized_path)
            target = documents_dir / source.name
            shutil.copyfile(source, target)
            target.chmod(0o444)
            prompt = prompt.replace(str(source), str(target))
            remapped.append(replace(item, normalized_path=str(target)))
        else:
            remapped.append(item)
    schema = workspace / "output-schema.json"
    shutil.copyfile(prepared.schema_path, schema)
    schema.chmod(0o444)
    (workspace / "manifest.json").write_text(json.dumps({"documents": [item.public_dict() for item in remapped]}, ensure_ascii=False, indent=2), encoding="utf-8")
    (workspace / "manifest.json").chmod(0o444)
    return replace(prepared, case_dir=workspace, normalized=remapped, schema_path=schema, prompt=prompt)


def run_stage(definition: StageDefinition, prepared: PreparedStage, provider: LLMProvider) -> dict[str, Any]:
    print(f"[{definition.identifier} llm] iniciando Codex", file=sys.stderr, flush=True)
    response = provider.generate(instructions=prepared.resources.instructions, prompt=prepared.prompt,
                                 schema_path=prepared.schema_path, case_dir=prepared.case_dir,
                                 output_paths=output_paths_for_run(prepared.run_dir))
    print(f"[{definition.identifier} llm] respuesta recibida", file=sys.stderr, flush=True)
    validation = definition.validate(response.data, prepared)
    print(f"[{definition.identifier} validación] {'correcta' if validation['valid'] else 'con errores'}", file=sys.stderr, flush=True)
    # Persist validation before raising: failed runs must remain diagnosable and
    # launchers can prove that no publication was attempted.
    _write_json(prepared.run_dir / "output" / "validation.json", validation)
    if not validation["valid"]:
        raise ValueError(f"La validación de {definition.identifier} falló; los diagnósticos se conservan en {prepared.run_dir}")
    outcome = definition.build_outcome(response, validation, prepared)
    for name, value in outcome.output_artifacts.items():
        _write_json(prepared.run_dir / "output" / name, value)
    _write_json(prepared.run_dir / "output" / definition.files.metrics, {
        "usage": response.usage, "execution": response.execution, "validation": outcome.metrics_validation,
    })
    if definition.postprocess:
        definition.postprocess(outcome, prepared)
    _write_json(prepared.run_dir / "output" / definition.files.result, outcome.result)
    return outcome.result


def _load_resources(system_prompt_path: Path, task_prompt_path: Path, prompt_version_path: Path,
                    config_path: Path, schema_path: Path,
                    rules_path: Path | None = None, version_bundle: dict[str, Any] | None = None) -> LoadedResources:
    return LoadedResources(
        instructions=system_prompt_path.read_text(encoding="utf-8"),
        task=task_prompt_path.read_text(encoding="utf-8"),
        prompt_version=prompt_version_path.read_text(encoding="utf-8").strip(),
        config=yaml.safe_load(config_path.read_text(encoding="utf-8")),
        schema=json.loads(schema_path.read_text(encoding="utf-8")), rules_path=rules_path,
        version_bundle=version_bundle,
    )


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
