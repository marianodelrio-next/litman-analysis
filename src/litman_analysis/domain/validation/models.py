from __future__ import annotations

from collections.abc import Callable

ValidationError = dict[str, object]
SemanticValidator = Callable[[dict], list[ValidationError]]


def validate_extraction(data: dict, schema: dict, document_ids: set[str],
                        semantic_validators: tuple[SemanticValidator, ...] = ()) -> dict:
    """Compone las comprobaciones comunes y las reglas declaradas por cada análisis.

    Conserva el contrato histórico de ``validation.json`` para que los consumidores
    existentes no requieran migración.
    """
    from .evidence import validate_document_references
    from .schema import validate_schema

    schema_errors = validate_schema(data, schema)
    evidence_errors = validate_document_references(data, document_ids)
    semantic_errors = [error for validator in semantic_validators for error in validator(data)]
    return {"valid": not schema_errors and not evidence_errors and not semantic_errors,
            "schema_errors": schema_errors, "evidence_errors": evidence_errors,
            "semantic_errors": semantic_errors}
