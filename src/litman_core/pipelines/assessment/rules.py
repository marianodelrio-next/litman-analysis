from __future__ import annotations

import unicodedata
from pathlib import Path

import yaml
from litman_core.domain.validation.evidence import evidence_ids_for


def load_rules(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or "").lower())
    return "".join(char for char in text if unicodedata.category(char) != "Mn")


def evaluate_rules(extraction: dict, config: dict, validation: dict | None = None,
                   evidence_index: dict | None = None) -> dict:
    if validation is not None and validation.get("valid") is not True:
        raise ValueError("No se puede evaluar comercialmente una extracción inválida")
    ficha = extraction.get("ficha", {})
    title = _norm(ficha.get("objeto_contrato"))
    summary = _norm(ficha.get("resumen"))
    organization = _norm(ficha.get("organismo"))
    combined = f" {title} {summary} "
    budget = ficha.get("presupuesto", {}).get("base_sin_iva")
    team = ficha.get("equipo", {}).get("numero_personas_exigido")
    lots = ficha.get("lotes", {}).get("existen") is True
    contract_type = _norm(ficha.get("tipo_contrato"))
    procedure = _norm(ficha.get("tipo_procedimiento"))
    new_stack = {_norm(item) for item in ficha.get("stack_tecnologico", {}).get("stack_nuevo_desarrollo", [])}
    certifications = ficha.get("certificaciones_exigidas", [])
    presence = ficha.get("presencialidad", {})
    strategic = any(_norm(customer) in organization for customer in config.get("strategic_customers", []))
    is_framework = any(term in f" {title} {procedure} " for term in (" sda ", "sistema dinamico", "acuerdo marco"))
    is_ai = any(term in combined for term in ("inteligencia artificial", " ia ", "machine learning"))
    reasons = []
    evaluations = []

    def record(rule: str, status: str, reason: str, fields: list[str], *, severity: str = "discard") -> None:
        evaluations.append({"rule_id": rule, "label": rule.replace("_", " ").capitalize(),
                            "status": status, "severity": severity, "explanation": reason,
                            "evidence_ids": evidence_ids_for(evidence_index or {}, *fields),
                            "policy_reference": f"{config['version']}:{rule}"})

    def discard(rule: str, reason: str, fields: list[str]) -> None:
        reasons.append({"regla": rule, "motivo": reason})
        record(rule, "triggered", reason, fields)

    limits = config["thresholds"]
    if budget is not None and budget < limits["budget_min"] and not strategic:
        discard("presupuesto_minimo", f"Presupuesto inferior a {limits['budget_min']} €", ["ficha.presupuesto.base_sin_iva"])
    else:
        record("presupuesto_minimo", "pass", "Presupuesto dentro del mínimo o excepción estratégica.", ["ficha.presupuesto.base_sin_iva", "ficha.organismo"])
    if budget is not None and budget > limits["budget_max"] and not is_framework and not is_ai:
        discard("presupuesto_maximo", f"Presupuesto superior a {limits['budget_max']} €", ["ficha.presupuesto.base_sin_iva", "ficha.objeto_contrato"])
    else:
        record("presupuesto_maximo", "pass", "Presupuesto dentro del máximo o excepción aplicable.", ["ficha.presupuesto.base_sin_iva", "ficha.objeto_contrato"])
    matched_title = sorted({_norm(term) for term in config["discard_title_terms"] if _norm(term) in title})
    if matched_title:
        discard("termino_titulo_excluido", "Título contiene: " + ", ".join(matched_title), ["ficha.objeto_contrato"])
    else:
        record("termino_titulo_excluido", "pass", "No contiene términos excluidos.", ["ficha.objeto_contrato"])
    supply = "suministro" in title or "suministro" in contract_type
    mixed_supply = supply and (lots or any(term in combined for term in ("servicio", "desarrollo", "automatizacion", "rpa", " ia ")))
    if supply and not mixed_supply:
        discard("suministro_puro", "Suministro sin señales de servicio, desarrollo o lotes", ["ficha.objeto_contrato", "ficha.tipo_contrato", "ficha.lotes"])
    else:
        record("suministro_puro", "not_applicable", "No es un suministro puro.", ["ficha.objeto_contrato", "ficha.tipo_contrato"])
    for cert in certifications:
        if "ens" in _norm(cert.get("nombre")) and cert.get("obligatoria") is True and _norm(cert.get("nivel")) in {"media", "alta"}:
            discard("ens_certificacion_media_alta", "Exige certificación ENS media o alta", ["ficha.certificaciones_exigidas"])
    if not any(item["rule_id"] == "ens_certificacion_media_alta" for item in evaluations):
        record("ens_certificacion_media_alta", "not_applicable", "No se ha detectado certificación ENS media o alta obligatoria.", ["ficha.certificaciones_exigidas"])
    if team is not None and team > limits["team_max"]:
        discard("equipo_maximo", f"Exige más de {limits['team_max']} personas", ["ficha.equipo.numero_personas_exigido"])
    else:
        record("equipo_maximo", "pass", "Equipo dentro del límite o no cuantificado.", ["ficha.equipo.numero_personas_exigido"])
    unwanted = {_norm(item) for item in config["unwanted_new_development_technologies"]}
    matched_stack = sorted(unwanted.intersection(new_stack))
    if matched_stack:
        discard("stack_nuevo_no_deseado", "Nuevo desarrollo en: " + ", ".join(matched_stack), ["ficha.stack_tecnologico.stack_nuevo_desarrollo"])
    else:
        record("stack_nuevo_no_deseado", "pass", "No se detecta stack nuevo excluido.", ["ficha.stack_tecnologico.stack_nuevo_desarrollo"])

    # Son alertas informativas: permanecen trazables, pero no introducen una
    # tercera acción comercial ni bloquean una decisión binaria válida.
    if is_ai and budget is not None and budget > limits["budget_max"]:
        record("ia_gran_presupuesto", "triggered", "Proyecto IA grande; valorar partner", ["ficha.objeto_contrato", "ficha.presupuesto.base_sin_iva"], severity="review")
    if mixed_supply:
        record("suministro_mixto", "triggered", "Revisar servicios y lotes por separado", ["ficha.objeto_contrato", "ficha.lotes"], severity="review")
    # Solo cuenta el trabajo presencial exigido; una reunión presencial
    # posible o puntual no debe activar esta revisión.
    if presence.get("exigida") is True and presence.get("modalidad") in {"habitual", "permanente", "mixta"}:
        record("presencialidad", "triggered", "Requiere valoración comercial", ["ficha.presencialidad"], severity="review")
    if extraction.get("calidad_informacion", {}).get("estado") != "suficiente":
        record("informacion_incompleta", "triggered", "Información parcial; requiere atención", [], severity="system")

    if reasons:
        return {"accion": "descartar", "motivos": reasons,
                "evaluaciones": evaluations, "permite_accion_automatica": True, "rules_version": config["version"]}

    positive = strategic or "audiovisual" in combined or any(_norm(term) in combined for term in config["positive_terms"])
    return {
        "accion": "continuar",
        "motivos": [{"regla": "senales_positivas" if positive else "sin_reglas_excluyentes",
                     "motivo": "Encaje inicial positivo" if positive else "No se detectan reglas excluyentes"}],
        "evaluaciones": evaluations, "permite_accion_automatica": True,
        "rules_version": config["version"],
    }
