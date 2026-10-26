from __future__ import annotations

from typing import Any

from .prompt import build_prompt
from .rules import evaluate_rules, load_rules
from litman_core.generation.opportunity_report import generate_opportunity_report
from litman_core.pipelines.registry import PIPELINES
from litman_core.domain.validation import validate_extraction
from litman_core.domain.validation.evidence import build_evidence_index, verification_errors

from litman_core.pipelines.models import PreparedStage, StageDefinition, StageOutcome, StagePreparation, StageResources


def definition() -> StageDefinition:
    pipeline = PIPELINES.get("assessment")
    def resources(settings):
        resolved = pipeline.resolve(settings.resource_root)
        return StageResources(
            resolved.paths["system_prompt"].parent, resolved.paths["config"], resolved.paths["schema"],
            rules_path=resolved.paths["rules"], version_bundle=resolved.version_bundle(),
            system_prompt_path=resolved.paths["system_prompt"], task_prompt_path=resolved.paths["task_prompt"],
            prompt_version_path=resolved.paths["prompt_version"])
    return StageDefinition(
        identifier=pipeline.identifier, version=pipeline.functional_version, resources=resources,
        prepare_prompt=_prepare_prompt, request_metadata=_request_metadata, validate=_validate,
        build_outcome=_build_outcome, postprocess=_postprocess,
        output_files=("extraction.json", "evidence-index.json", "validation.json", "decision.json", "result.json", "metrics.json"),
    )


def _prepare_prompt(resources, documents, normalized, context: dict[str, Any]) -> StagePreparation:
    if resources.rules_path is None:
        raise ValueError("El análisis inicial requiere un fichero de reglas")
    rules = load_rules(resources.rules_path)
    return StagePreparation(
        build_prompt(resources.task, documents, normalized, resources.config),
        context={"rules": rules},
    )


def _request_metadata(settings, resources, normalized, context) -> dict:
    return {"rules_version": context["rules"]["version"],
            "normalized_documents": [doc.normalized_path for doc in normalized if doc.normalized_path]}


def _validate(data: dict, prepared: PreparedStage) -> dict:
    validation = validate_extraction(data, prepared.resources.schema, {doc.document_id for doc in prepared.documents})
    evidence_index = build_evidence_index(data, prepared.documents, prepared.normalized)
    errors = verification_errors(evidence_index)
    validation["evidence_verification_errors"] = errors
    validation["complete"] = not errors
    validation["warnings"] = ([{"kind": "unverified_evidence", "count": len(errors)}]
                              if errors else [])
    ready = {item.document_id for item in prepared.normalized if item.status == "ready"}
    processed = {item.get("documento_id") for item in data.get("control_documental", {}).get("documentos", []) if item.get("procesado") is True}
    if ready and not (ready & processed):
        validation["document_processing_errors"] = ["Hay documentos normalizados ready pero el agente no marcó ninguno como procesado"]
        validation["valid"] = False
    prepared.context["evidence_index"] = evidence_index
    return validation


def _build_outcome(response, validation: dict, prepared: PreparedStage) -> StageOutcome:
    evidence_index = prepared.context["evidence_index"]
    decision = evaluate_rules(response.data, prepared.context["rules"], validation, evidence_index)
    result = {
        "metadata": {"case_dir": str(prepared.case_dir), "provider": response.provider, "model": response.model,
                     "response_id": response.response_id, "prompt_version": prepared.resources.prompt_version,
                     "rules_version": prepared.context["rules"]["version"], "execution": response.execution},
        "extraction": response.data, "validation": validation, "decision": decision,
    }
    return StageOutcome(result, {
        "extraction.json": response.data, "evidence-index.json": evidence_index, "validation.json": validation,
        "decision.json": decision, "result.json": result,
    }, {"valid": validation["valid"],
        "error_count": len(validation.get("schema_errors", [])) + len(validation.get("evidence_errors", []))})


def _postprocess(outcome: StageOutcome, prepared: PreparedStage) -> None:
    outcome.result["report"] = generate_opportunity_report(prepared.run_dir)
