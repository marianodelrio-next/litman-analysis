from __future__ import annotations

from .models import ValidationError


def detailed_analysis_economic_semantic_errors(data: dict) -> list[ValidationError]:
    """Reglas económicas que complementan el esquema del análisis detallado."""
    economic = data.get("simulador_economico")
    if not isinstance(economic, dict):
        return []
    errors: list[ValidationError] = []
    formula = economic.get("formula_precio") or {}
    if formula.get("tipo") not in (None, "no_localizada"):
        if not formula.get("expresion_literal"):
            errors.append({"path": "simulador_economico.formula_precio.expresion_literal",
                           "message": "La fórmula clasificada debe conservar su expresión literal"})
        if not formula.get("evidencia"):
            errors.append({"path": "simulador_economico.formula_precio.evidencia",
                           "message": "La fórmula económica debe tener evidencia"})
    for index, criterion in enumerate(economic.get("criterios_no_precio", [])):
        if not criterion.get("evidencia"):
            errors.append({"path": f"simulador_economico.criterios_no_precio.{index}.evidencia",
                           "message": "El criterio debe tener evidencia"})
    for index, rule in enumerate((economic.get("baja_anormal") or {}).get("reglas", [])):
        maximum = rule.get("max_licitadores")
        if maximum is not None and maximum < rule.get("min_licitadores", 1):
            errors.append({"path": f"simulador_economico.baja_anormal.reglas.{index}",
                           "message": "El rango de licitadores es incoherente"})
    return errors
