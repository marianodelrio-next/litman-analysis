from pathlib import Path

from litman_analysis.pipelines.assessment.rules import evaluate_rules, load_rules
from litman_analysis.resource_paths import resource_path


RULES = load_rules(resource_path("pipelines", "assessment", "v1", "rules.yaml"))


def extraction(**overrides):
    ficha = {
        "objeto_contrato": "Desarrollo de cuadros de mando",
        "organismo": "Organismo de prueba",
        "resumen": "Servicio de Business Intelligence",
        "presupuesto": {"base_sin_iva": 100000},
        "equipo": {"numero_personas_exigido": 5},
        "lotes": {"existen": False},
        "tipo_contrato": "Servicios", "tipo_procedimiento": "Abierto",
        "stack_tecnologico": {"tecnologias": ["Power BI"], "stack_nuevo_desarrollo": ["Power BI"]},
        "certificaciones_exigidas": [], "presencialidad": {"exigida": False},
    }
    ficha.update(overrides)
    return {"ficha": ficha, "calidad_informacion": {"estado": "suficiente"}}


def test_low_budget_is_discarded() -> None:
    assert evaluate_rules(extraction(presupuesto={"base_sin_iva": 39999}), RULES)["accion"] == "descartar"


def test_strategic_customer_survives_low_budget() -> None:
    data = extraction(organismo="Bilbao TIK", presupuesto={"base_sin_iva": 30000})
    assert evaluate_rules(data, RULES)["accion"] == "continuar"


def test_mixed_supply_continues_with_alert() -> None:
    data = extraction(objeto_contrato="Suministro y desarrollo RPA", tipo_contrato="Suministro")
    decision = evaluate_rules(data, RULES)
    assert decision["accion"] == "continuar"
    assert any(item["rule_id"] == "suministro_mixto" for item in decision["evaluaciones"])


def test_high_budget_ai_continues_with_alert() -> None:
    data = extraction(objeto_contrato="Proyecto de inteligencia artificial", presupuesto={"base_sin_iva": 3000000})
    decision = evaluate_rules(data, RULES)
    assert decision["accion"] == "continuar"
    assert any(item["rule_id"] == "ia_gran_presupuesto" for item in decision["evaluaciones"])


def test_ens_high_is_discarded_only_when_certification_is_required() -> None:
    data = extraction(certificaciones_exigidas=[{"nombre": "ENS", "nivel": "alta", "obligatoria": True}])
    assert evaluate_rules(data, RULES)["accion"] == "descartar"


def test_inherited_php_does_not_discard() -> None:
    data = extraction(stack_tecnologico={"tecnologias": ["PHP", "Java"], "stack_nuevo_desarrollo": ["Java"]})
    assert evaluate_rules(data, RULES)["accion"] == "continuar"


def test_presence_and_partial_information_continue_with_alerts() -> None:
    data = extraction(presencialidad={"exigida": True, "modalidad": "habitual"})
    data["calidad_informacion"]["estado"] = "parcial"
    decision = evaluate_rules(data, RULES)
    assert decision["accion"] == "continuar"
    assert {"presencialidad", "informacion_incompleta"}.issubset(
        {item["rule_id"] for item in decision["evaluaciones"]}
    )


def test_no_positive_signals_still_continues_and_never_reviews() -> None:
    data = extraction(objeto_contrato="Asistencia", resumen="Apoyo general",
                      stack_tecnologico={"tecnologias": [], "stack_nuevo_desarrollo": []})
    decision = evaluate_rules(data, RULES)
    assert decision["accion"] == "continuar"
    assert decision["motivos"][0]["motivo"] == "No se detectan reglas excluyentes"
    assert decision["accion"] != "revisar"


def test_invalid_validation_is_a_technical_failure() -> None:
    import pytest
    with pytest.raises(ValueError, match="extracción inválida"):
        evaluate_rules(extraction(), RULES, {"valid": False})
