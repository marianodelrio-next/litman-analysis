from litman_analysis.domain.validation import validate_extraction
from litman_analysis.domain.validation.semantic import detailed_analysis_economic_semantic_errors


def test_invalid_schema_is_reported() -> None:
    result = validate_extraction({"amount": "invalid"}, {"type": "object", "properties": {"amount": {"type": "number"}}}, set())
    assert not result["valid"]
    assert result["schema_errors"][0]["path"] == "amount"


def test_nested_evidence_document_is_validated() -> None:
    schema = {"type": "object"}
    data = {
        "memoria_tecnica": {
            "secciones": [{
                "evidencias": [{"documento_id": "missing", "pagina": 1, "texto_citado": "texto"}]
            }]
        }
    }
    result = validate_extraction(data, schema, {"existing"})
    assert not result["valid"]
    assert result["evidence_errors"][0]["path"] == "memoria_tecnica.secciones.0.evidencias.0"


def test_economic_formula_requires_traceable_evidence() -> None:
    data = {
        "simulador_economico": {
            "formula_precio": {"tipo": "inversa_oferta_minima", "expresion_literal": "P=min/precio"},
            "criterios_no_precio": [], "baja_anormal": {"reglas": []},
        }
    }
    result = validate_extraction(data, {"type": "object"}, set(), (detailed_analysis_economic_semantic_errors,))
    assert not result["valid"]
    assert result["semantic_errors"][0]["path"].endswith("evidencia")


def test_composes_multiple_semantic_validations() -> None:
    def first(_: dict) -> list[dict]:
        return [{"path": "one", "message": "first"}]

    def second(_: dict) -> list[dict]:
        return [{"path": "two", "message": "second"}]

    result = validate_extraction({}, {"type": "object"}, set(), (first, second))
    assert [error["path"] for error in result["semantic_errors"]] == ["one", "two"]
