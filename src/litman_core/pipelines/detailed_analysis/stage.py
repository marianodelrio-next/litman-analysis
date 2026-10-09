from __future__ import annotations

from typing import Any
import json

from .prompt import build_prompt
from litman_core.pipelines.registry import PIPELINES
from litman_core.domain.validation import validate_extraction
from litman_core.domain.validation.evidence import build_evidence_index, verification_errors
from litman_core.domain.validation.semantic import detailed_analysis_economic_semantic_errors
from litman_core.infrastructure.runs import dossier_lineage

from litman_core.pipelines.models import PreparedStage, StageDefinition, StageOutcome, StagePreparation, StageResources


def definition() -> StageDefinition:
    pipeline = PIPELINES.get("detailed-analysis")
    def resources(settings):
        resolved = pipeline.resolve(settings.resource_root)
        return StageResources(
            resolved.paths["system_prompt"].parent, resolved.paths["config"], resolved.paths["schema"],
            version_bundle=resolved.version_bundle(), system_prompt_path=resolved.paths["system_prompt"],
            task_prompt_path=resolved.paths["task_prompt"], prompt_version_path=resolved.paths["prompt_version"])
    return StageDefinition(
        identifier=pipeline.identifier, version=pipeline.functional_version, resources=resources,
        prepare_prompt=_prepare_prompt, request_metadata=_request_metadata, validate=_validate,
        build_outcome=_build_outcome, postprocess=_postprocess,
        output_files=("dossier.json", "validation.json", "result.json", "metrics.json"),
    )


def _prepare_prompt(resources, documents, normalized, context: dict[str, Any]) -> StagePreparation:
    assessment_result = context.get("assessment_result")
    artifacts = {"assessment_result.json": assessment_result} if assessment_result else {}
    return StagePreparation(build_prompt(resources.task, documents, normalized, resources.config, assessment_result),
                            input_artifacts=artifacts)


def _request_metadata(settings, resources, normalized, context) -> dict:
        return {"model": settings.codex_model}


def _validate(data: dict, prepared: PreparedStage) -> dict:
    validation = validate_extraction(
        data, prepared.resources.schema, {doc.document_id for doc in prepared.documents},
        semantic_validators=(detailed_analysis_economic_semantic_errors,),
    )
    index = build_evidence_index(data, prepared.documents, prepared.normalized)
    errors = verification_errors(index)
    validation["evidence_verification_errors"] = errors
    validation["complete"] = not errors
    validation["warnings"] = ([{"kind": "unverified_evidence", "count": len(errors)}]
                              if errors else [])
    ready = {item.document_id for item in prepared.normalized if item.status == "ready"}
    cited = {item.get("documento_id") for item in data.get("evidencias", []) if item.get("documento_id")}
    if ready and not (ready & cited):
        validation["document_processing_errors"] = ["Hay documentos normalizados ready sin evidencia de lectura"]
        validation["valid"] = False
    return validation


def _build_outcome(response, validation: dict, prepared: PreparedStage) -> StageOutcome:
    result = {
        "metadata": {"case_dir": str(prepared.case_dir), "provider": response.provider, "model": response.model,
                     "response_id": response.response_id, "prompt_version": prepared.resources.prompt_version,
                     "config_version": prepared.resources.config["version"], "execution": response.execution},
        "dossier": response.data, "validation": validation,
    }
    return StageOutcome(result, {"dossier.json": response.data, "validation.json": validation, "result.json": result},
                        {"valid": validation["valid"], "error_count": (
                            len(validation.get("schema_errors", [])) + len(validation.get("evidence_errors", [])) +
                            len(validation.get("semantic_errors", [])) +
                            len(validation.get("evidence_verification_errors", [])))})


def _postprocess(_outcome: StageOutcome, prepared: PreparedStage) -> None:
    """Publish dossier provenance once its serialized bytes are final."""
    dossier = prepared.run_dir / "output" / "dossier.json"
    lineage = dossier_lineage(stage="detailed-analysis", run_dir=prepared.run_dir, dossier_path=dossier,
                              case_dir=prepared.case_dir, origin="explicit")
    (prepared.run_dir / "lineage.json").write_text(
        json.dumps(lineage, ensure_ascii=False, indent=2), encoding="utf-8")
