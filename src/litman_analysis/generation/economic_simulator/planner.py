from __future__ import annotations

from copy import deepcopy


SUPPORTED_PRICE_FORMULAS = {"inversa_oferta_minima"}


def build_economic_plan(dossier: dict, template_id: str = "standard-v1") -> dict:
    source = dossier.get("simulador_economico") or {}
    formula = source.get("formula_precio") or {}
    criteria = []
    for index, item in enumerate(source.get("criterios_no_precio", []), 1):
        criteria.append({
            "id": f"criterion-{index:03d}",
            "order": index,
            "name": item.get("nombre") or f"Criterio {index}",
            "type": item.get("tipo"),
            "max_points": item.get("puntuacion_maxima"),
            "min_value": item.get("valor_minimo"),
            "max_value": item.get("valor_maximo"),
            "unit": item.get("unidad"),
            "description": item.get("descripcion"),
            "evidence": item.get("evidencia"),
        })

    warnings = list(source.get("advertencias", []))
    abnormal = deepcopy(source.get("baja_anormal") or {})
    warnings.extend(abnormal.get("advertencias", []))
    for rule in abnormal.get("reglas", []):
        base = rule.get("base")
        if isinstance(base, (int, float)) and 1 < base <= 100:
            rule["base"] = base / 100
            warnings.append(
                f"Base de baja anormal normalizada de {base}% a {rule['base']}."
            )
    price_supported = formula.get("tipo") in SUPPORTED_PRICE_FORMULAS
    if not price_supported:
        warnings.append(
            "La fórmula económica no está soportada para cálculo automático; "
            "se conserva como texto y queda pendiente de implementación."
        )
    modeled = sum(item.get("max_points") or 0 for item in criteria) + (formula.get("puntuacion_maxima") or 0)
    declared = source.get("puntuacion_total")
    if declared is not None and abs(modeled - declared) > 1e-9:
        warnings.append(
            f"La puntuación declarada ({declared}) no coincide con la suma modelada ({modeled})."
        )
    qualitative = sum(item.get("max_points") or 0 for item in criteria)
    threshold_maximum = abnormal.get("maximo_cualitativo")
    if threshold_maximum is not None and abs(qualitative - threshold_maximum) > 1e-9:
        warnings.append(
            f"Los criterios no económicos suman {qualitative}, pero el umbral de baja "
            f"anormal usa {threshold_maximum}. Se conservan ambos valores del pliego."
        )
    return {
        "version": "economic-plan-v1",
        "template_id": template_id,
        "tender": {
            "name": dossier.get("cabecera", {}).get("nombre"),
            "reference": dossier.get("cabecera", {}).get("expediente"),
            "budget_without_tax": source.get("presupuesto_maximo_sin_iva"),
            "currency": source.get("moneda") or dossier.get("cabecera", {}).get("moneda"),
        },
        "total_points": declared,
        "price_formula": {
            "type": formula.get("tipo"),
            "literal": formula.get("expresion_literal"),
            "max_points": formula.get("puntuacion_maxima"),
            "rounding_decimals": formula.get("redondeo_decimales"),
            "evidence": formula.get("evidencia"),
            "supported": price_supported,
        },
        "criteria": criteria,
        "abnormally_low": abnormal,
        "restrictions": source.get("restricciones", []),
        "warnings": list(dict.fromkeys(warnings)),
    }


def skeleton_economic_inputs(plan: dict, scenario_names: list[str], competitor_slots: int) -> dict:
    bidders = [{"name": "NEXT", "price": None, "criterion_scores": {}}]
    bidders.extend({"name": f"LICITADOR {index}", "price": None, "criterion_scores": {}}
                   for index in range(1, competitor_slots + 1))
    return {
        "version": "economic-inputs-v1",
        "scenarios": [
            {"id": f"scenario-{index:02d}", "name": name,
             "bidders": [dict(item, criterion_scores={}) for item in bidders]}
            for index, name in enumerate(scenario_names, 1)
        ],
        "notes": [
            "Completar el precio y las puntuaciones previstas de NEXT.",
            "Los datos de otros licitadores son hipótesis internas, no hechos del expediente.",
        ],
    }
