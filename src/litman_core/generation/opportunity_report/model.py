from __future__ import annotations

_CONFIRM = {"objeto_contrato":"objeto del contrato", "numero_expediente":"número de expediente", "organismo":"organismo contratante", "presupuesto":"presupuesto", "fecha_limite_presentacion":"fecha límite", "duracion_contrato":"duración", "certificaciones_exigidas":"certificaciones", "equipo":"equipo requerido", "stack_tecnologico":"stack tecnológico", "presencialidad":"presencialidad", "subcontratacion":"subcontratación", "solvencia_tecnica":"solvencia técnica", "solvencia_economica":"solvencia económica", "tipo_procedimiento":"procedimiento", "cpv":"códigos CPV", "lotes":"lotes"}

def build_report_model(result: dict, evidence_index: dict, template: dict) -> dict:
    extraction, decision, validation = result["extraction"], result["decision"], result.get("validation", {})
    ficha, quality = extraction.get("ficha", {}), extraction.get("calidad_informacion", {})
    evidence = {x["evidence_id"]: x for x in evidence_index.get("evidences", [])}
    def sources(*requested):
        return list(dict.fromkeys(i for wanted in requested for field, ids in evidence_index.get("by_field", {}).items() if field == wanted or field.startswith(wanted + ".") or wanted.startswith(field + ".") for i in ids))
    def fact(label, value, *fields): return {"label": label, "value": _display(value), "source_ids": sources(*fields)}
    budget, team = ficha.get("presupuesto") or {}, ficha.get("equipo") or {}
    facts = [fact("Presupuesto sin IVA", _money(budget.get("base_sin_iva"), budget.get("moneda")), "ficha.presupuesto.base_sin_iva"), fact("Fecha límite", _date(ficha.get("fecha_limite_presentacion")), "ficha.fecha_limite_presentacion"), fact("Duración", ficha.get("duracion_contrato"), "ficha.duracion_contrato"), fact("Equipo mínimo", _people(team.get("numero_personas_exigido")), "ficha.equipo.numero_personas_exigido")]
    overview = _overview(ficha, validation, sources, quality)
    evaluations = decision.get("evaluaciones", [])
    checks = [{"label": x.get("label", x.get("rule_id")), "status": x.get("status"), "status_label": _status_label(x.get("status")), "text": x.get("explanation"), "source_ids": x.get("evidence_ids", [])} for x in evaluations]
    alerts = [{"text": x["explanation"], "severity": x.get("severity", "review"), "source_ids": x.get("evidence_ids", [])} for x in evaluations if x.get("status") == "triggered"]
    alerts += [{"text": x, "severity": "review", "source_ids": sources("calidad_informacion.contradicciones")} for x in quality.get("contradicciones", [])]
    alerts += [{"text": x, "severity": "system", "source_ids": []} for x in quality.get("limitaciones", [])[:2]]
    positives = [{"text": x, "source_ids": sources("clasificacion.senales_positivas")} for x in extraction.get("clasificacion", {}).get("senales_positivas", [])[:4]]
    used = [i for group in (facts, overview["found"], alerts, positives, checks) for x in group for i in x.get("source_ids", [])]
    selected = [evidence[x] for x in dict.fromkeys(used) if x in evidence][:template.get("limits", {}).get("sources", 8)]
    refs = {x["evidence_id"]: f"F{i}" for i, x in enumerate(selected, 1)}
    for group in (facts, overview["found"], alerts, positives, checks):
        for item in group: item["references"] = [refs[x] for x in item.pop("source_ids", []) if x in refs]
    documents = extraction.get("control_documental", {}).get("documentos", [])
    return {"version":"opportunity-report-v4", "template":{"id":template["id"], "version":template["version"]}, "header":{"title":_short_title(ficha.get("objeto_contrato")), "object":ficha.get("objeto_contrato"), "organization":ficha.get("organismo"), "contract_id":ficha.get("numero_expediente")}, "key_facts":facts, "summary":ficha.get("resumen") or "No consta resumen del expediente.", "tags":extraction.get("clasificacion", {}).get("tipologias", [])[:5], "positive_reasons":positives, "alerts":alerts, "rule_checks":checks, "rule_summary":{"triggered":sum(x["status"] == "triggered" for x in checks), "passed":sum(x["status"] == "pass" for x in checks), "not_applicable":sum(x["status"] == "not_applicable" for x in checks), "other":sum(x["status"] not in {"triggered","pass","not_applicable"} for x in checks)}, "information_overview":overview, "information_quality":{"status":quality.get("estado") or "no consta"}, "conditions":[fact("Procedimiento", ficha.get("tipo_procedimiento"), "ficha.tipo_procedimiento"), fact("Lotes", _yes_no((ficha.get("lotes") or {}).get("existen")), "ficha.lotes"), fact("Presencialidad", (ficha.get("presencialidad") or {}).get("modalidad"), "ficha.presencialidad"), fact("Subcontratación", ficha.get("subcontratacion"), "ficha.subcontratacion")], "document_control":documents, "document_summary":{"received":len(documents), "processed":sum(x.get("procesado") is True for x in documents)}, "missing_documents":extraction.get("control_documental", {}).get("ausencias_relevantes", []), "sources":[{"ref":refs[x["evidence_id"]], **x} for x in selected]}

def _overview(ficha, validation, sources, quality):
    found, missing = [], []
    def yes(text, field): found.append({"text":text, "source_ids":sources("ficha." + field)})
    stack, team = ficha.get("stack_tecnologico") or {}, ficha.get("equipo") or {}
    tech = stack.get("tecnologias") or stack.get("stack_nuevo_desarrollo") or []
    if tech: yes("Se han identificado las tecnologías principales: " + ", ".join(map(str, tech[:4])) + ".", "stack_tecnologico")
    else: missing.append({"text":"No se ha identificado un stack tecnológico concreto."})
    certs = ficha.get("certificaciones_exigidas") or []
    if certs: yes("Se han localizado certificaciones exigidas.", "certificaciones_exigidas")
    else: missing.append({"text":"No se han localizado certificaciones exigidas."})
    tech_sol, econ_sol = ficha.get("solvencia_tecnica"), ficha.get("solvencia_economica")
    if tech_sol and econ_sol: yes("Se han localizado requisitos de solvencia técnica y económica.", "solvencia_tecnica")
    elif tech_sol: yes("Se han localizado requisitos de solvencia técnica.", "solvencia_tecnica"); missing.append({"text":"No se han localizado requisitos de solvencia económica."})
    elif econ_sol: yes("Se han localizado requisitos de solvencia económica.", "solvencia_economica"); missing.append({"text":"No se han localizado requisitos de solvencia técnica."})
    else: missing.append({"text":"No se han localizado requisitos de solvencia técnica ni económica."})
    if team.get("numero_personas_exigido") is not None: yes(f"Se exige un equipo mínimo de {team['numero_personas_exigido']} personas.", "equipo")
    elif team.get("perfiles"): yes("Se han identificado perfiles profesionales requeridos, pero no un número mínimo de personas.", "equipo"); missing.append({"text":"No consta un número mínimo de personas para el equipo."})
    else: missing.append({"text":"No se ha localizado información sobre el equipo requerido."})
    if ficha.get("fecha_limite_presentacion") is None: missing.append({"text":"No se ha localizado la fecha límite de presentación."})
    presence = ficha.get("presencialidad") or {}
    if presence.get("exigida") is True or presence.get("modalidad"): yes(f"La prestación incluye presencialidad {presence.get('modalidad') or 'indicada'}.", "presencialidad")
    elif presence.get("exigida") is None: missing.append({"text":"No consta el régimen de presencialidad."})
    lots = ficha.get("lotes") or {}
    if lots.get("existen") is False: yes("No hay división en lotes.", "lotes")
    elif lots.get("existen") is None: missing.append({"text":"No se ha podido determinar si el contrato está dividido en lotes."})
    concepts = []
    for error in validation.get("evidence_verification_errors") or []:
        path = str(error.get("path") or "")
        key = next((k for k in _CONFIRM if path == "ficha." + k or path.startswith("ficha." + k + ".")), None)
        if key and _CONFIRM[key] not in concepts: concepts.append(_CONFIRM[key])
    priority = ["duración", "equipo requerido", "stack tecnológico", "subcontratación", "procedimiento", "certificaciones", "presupuesto", "fecha límite", "presencialidad", "solvencia técnica", "solvencia económica", "lotes", "códigos CPV", "objeto del contrato", "número de expediente", "organismo contratante"]
    concepts = sorted(concepts, key=lambda item: priority.index(item))[:6]
    if not sources("ficha"): message = "No se dispone de referencias suficientes para comprobar automáticamente los datos principales."
    elif concepts: message = "Si se decide avanzar, conviene confirmar directamente en los pliegos: " + ", ".join(concepts) + "."
    else: message = "Los datos principales utilizados en esta valoración tienen referencias documentales localizables."
    return {"status":quality.get("estado") or "no consta", "status_label":"Información " + (quality.get("estado") or "disponible"), "found":found[:6], "missing":missing[:6], "to_confirm":concepts, "confirmation_message":message}

def _status_label(status): return {"triggered":"NO SUPERADA", "pass":"SUPERADA", "not_applicable":"NO APLICA", "unknown":"SIN DETERMINAR"}.get(str(status), str(status or "SIN ESTADO").upper())
def _display(value): return "No consta" if value is None or value == "" else str(value)
def _money(value, currency): return "No consta" if value is None else f"{float(value):,.2f} {(currency or 'EUR')}".replace(",","X").replace(".",",").replace("X",".")
def _date(value): return "No consta" if not value else str(value).replace("T", " · ")
def _people(value): return "No consta" if value is None else f"{value} personas"
def _yes_no(value): return "Sí" if value is True else "No" if value is False else "No consta"
def _short_title(value): return " ".join(str(value or "Oportunidad sin título").split()[:12])
def _truncate(value, size): return value if len(value) <= size else value[:size-1].rsplit(" ",1)[0] + "…"
