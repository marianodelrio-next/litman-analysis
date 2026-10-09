from __future__ import annotations

import re
import unicodedata


DEFAULT_SECTION_TITLES = (
    "Resumen ejecutivo",
    "Comprensión del proyecto",
    "Objetivos y alcance",
    "Propuesta técnica",
    "Plan de trabajo, fases y entregables",
    "Equipo requerido",
)

SUPPORTED_LANGUAGES = ("es",)


def build_document_plan(dossier: dict, template_id: str = "next-standard-v1") -> dict:
    memory = dossier.get("memoria_tecnica") or {}
    language = "es"
    specified = sorted(memory.get("secciones") or [], key=lambda item: item.get("orden", 0))
    structure_source = "tender" if specified else "detailed-analysis-suggestion"
    if specified:
        sections = [_specified_section(item, dossier, index, language) for index, item in enumerate(specified, 1)]
    else:
        suggested = [title for title in dossier.get("estructura_documento_tecnico", []) if title]
        titles = suggested or list(DEFAULT_SECTION_TITLES)
        structure_source = "detailed-analysis-suggestion" if suggested else "fallback"
        sections = [_fallback_section(title, dossier, index, language) for index, title in enumerate(titles, 1)]

    formatting = memory.get("formato") or _empty_format()
    word_budget = _apply_global_word_budget(sections, formatting.get("paginas_maximas"))
    pending = _constraint_pending(memory)
    identity = _document_identity(dossier, memory)
    pending.extend(identity.pop("pending"))
    return {
        "version": "document-plan-v2",
        "template_id": template_id,
        "identity": identity,
        "document_title": identity["document_title"],
        "language": language,
        "source_language": memory.get("idioma"),
        "structure_source": structure_source,
        "sections": sections,
        "formal_constraints": formatting,
        "word_budget": word_budget,
        "rules": memory.get("reglas") or [],
        "limit_scope": {
            "cover_counts": memory.get("portada_computa_limite"),
            "index_counts": memory.get("indice_computa_limite"),
            "annexes_count": memory.get("anexos_computan_limite"),
        },
        "pending_decisions": pending,
    }


def normalize_output_language(value: str | None) -> str:
    """La salida del producto es siempre española; el idioma fuente es descriptivo."""
    return "es"


def _specified_section(item: dict, dossier: dict, index: int, language: str) -> dict:
    source_title = item["titulo"]
    title = _presentation_title(source_title, index)
    translated = title == source_title
    criteria = _matching_criteria(source_title, dossier)
    score_info = _resolve_score(item.get("puntuacion"), criteria, dossier)
    score = score_info["score"]
    page_limit = item.get("limite_paginas")
    return {
        "id": f"section-{index:03d}-{_slug(source_title)}",
        "order": index,
        "title": title,
        "source_title": source_title,
        "purpose": item.get("descripcion") if translated and item.get("descripcion") else _contextual_purpose(title, dossier, language),
        "required": item.get("obligatoria") is not False,
        "score": score,
        **score_info,
        "display_title": display_title(title, score, language),
        "page_limit": page_limit,
        "target_words": _target_words(score, page_limit),
        "requirements": item.get("requisitos_relacionados") or _matching_requirements(source_title, dossier),
        "criteria": criteria,
        "evidence_fields": _section_evidence_fields(item, dossier),
        "subsections": _subsections(item, dossier, index, language),
        "guidance": _guidance(title, item.get("descripcion") if translated else None, dossier, score, page_limit,
                              item.get("requisitos_relacionados") or _matching_requirements(source_title, dossier), criteria,
                              _section_evidence_fields(item, dossier), item.get("evidencias", []), language),
        "generation_status": "ready",
    }


def _fallback_section(title: str, dossier: dict, index: int, language: str) -> dict:
    source_title = title
    title = _presentation_title(source_title, index)
    criteria = _matching_criteria(source_title, dossier)
    score_info = _resolve_score(None, criteria, dossier)
    score = score_info["score"]
    return {
        "id": f"section-{index:03d}-{_slug(source_title)}",
        "order": index,
        "title": title,
        "source_title": source_title,
        "purpose": "Estructura propuesta al no haberse localizado un índice obligatorio en el expediente.",
        "required": True,
        "score": score,
        **score_info,
        "display_title": display_title(title, score, language),
        "page_limit": None,
        "target_words": 500,
        "requirements": _matching_requirements(source_title, dossier),
        "criteria": criteria,
        "evidence_fields": _matching_evidence_fields(title, dossier),
        "subsections": _proposed_subsections(title, dossier, index, language),
        "guidance": _guidance(title, None, dossier, score, None, _matching_requirements(title, dossier), criteria,
                              _matching_evidence_fields(title, dossier), [], language),
        "generation_status": "ready",
    }


def _document_identity(dossier: dict, memory: dict) -> dict:
    header = dossier.get("cabecera") or {}
    name, reference = (header.get("nombre") or "").strip(), (header.get("expediente") or "").strip()
    doc_type = "Propuesta técnica"
    fallback = (memory.get("nombre_documento") or "").strip()
    if name:
        visible = name if not reference or reference.casefold() in name.casefold() else f"{name}\nExpte. {reference}"
    elif fallback and reference:
        visible = f"{fallback}\nExpte. {reference}"
    elif reference:
        visible = f"{doc_type}. Expte. {reference}"
    else:
        visible = doc_type
    short_source = name or fallback
    return {"document_type": doc_type, "tender_title": name or None, "tender_reference": reference or None,
            "short_title": _short_title(short_source, reference), "document_title": visible,
            "pending": [] if name or reference else ["No se ha localizado nombre ni expediente de la licitación."]}


def _short_title(value: str, reference: str) -> str | None:
    words = re.findall(r"[\wÁÉÍÓÚÜÑáéíóúüñ]+", value)
    reference_words = {word.casefold() for word in re.findall(r"\w+", reference)}
    stop = {"de", "del", "la", "las", "el", "los", "y", "a", "para", "en", "por", "servicio", "contratacion", "contratación", "suministro", "aplicaciones"}
    retained = [word for word in words if word.casefold() not in stop and word.casefold() not in reference_words]
    # Siglas y términos finales entre paréntesis suelen contener la identidad del expediente.
    meaningful = [word for word in retained if len(word) > 2 or word.isupper()]
    return " ".join(meaningful) or None


def _subsections(item: dict, dossier: dict, index: int, language: str) -> list[dict]:
    explicit = item.get("subapartados") or []
    if explicit:
        return [{"id": f"section-{index:03d}-{_slug(item['titulo'])}-sub-{position:02d}-{_slug(x['titulo'])}",
                 "title": _presentation_title(x["titulo"], position), "source_title": x["titulo"], "level": x.get("nivel", 2), "source": "tender",
                 "purpose": x.get("descripcion") if _presentation_title(x["titulo"], position) == x["titulo"] and x.get("descripcion") else _contextual_purpose(_presentation_title(x["titulo"], position), dossier, language),
                 "requirements": x.get("requisitos_relacionados") or [], "criteria": [],
                 "evidence_fields": [e.get("campo") for e in x.get("evidencias", []) if e.get("campo")]}
                for position, x in enumerate(explicit, 1)]
    return _proposed_subsections(item["titulo"], dossier, index, language)


def _proposed_subsections(title: str, dossier: dict, index: int, language: str) -> list[dict]:
    lowered = title.casefold()
    catalog = {
        "method": ["Principios metodológicos", "Organización de las actividades", "Validación y control de calidad", "Seguimiento y mejora continua"],
        "plan": ["Enfoque general del plan", "Fases y actividades", "Hitos y entregables", "Seguimiento y control", "Riesgos y dependencias"],
        "team": ["Organización del equipo", "Perfiles y responsabilidades", "Modelo de coordinación", "Disponibilidad y continuidad pendiente de confirmar"],
        "solution": ["Arquitectura funcional", "Componentes e integraciones", "Datos, seguridad y gobierno", "Despliegue y operación", "Decisiones técnicas pendientes"],
        "scope": ["Contexto y situación de partida", "Procesos y usuarios incluidos", "Necesidades funcionales", "Casos de uso y resultados esperados", "Condicionantes del alcance"],
        "other": ["Objetivo y alcance del apartado", "Contenido y evidencias a aportar"],
    }
    if any(term in lowered for term in ("metodolog", "metodología", "methodolog")):
        candidates = catalog["method"]
    elif any(term in lowered for term in ("plan", "fase", "cronograma", "entregable", "hito")):
        candidates = catalog["plan"]
    elif any(term in lowered for term in ("equipo", "perfil", "recursos", "team", "profile", "resources")):
        candidates = catalog["team"]
    elif any(term in lowered for term in ("arquitect", "solución", "tecnolog", "tecnica", "técnica", "solution", "technical")):
        candidates = catalog["solution"]
    elif any(term in lowered for term in ("alcance", "diseño", "funcional", "comprensi", "comprensión", "scope", "design", "understanding")):
        candidates = catalog["scope"]
    else:
        candidates = catalog["other"]
    candidates = list(dict.fromkeys(candidates))[:5]
    return [{"id": f"section-{index:03d}-{_slug(title)}-sub-{position:02d}-{_slug(name)}", "title": name,
             "level": 2, "source": "proposed", "purpose": _contextual_purpose(name, dossier, language),
             "requirements": [], "criteria": [], "evidence_fields": _matching_evidence_fields(name, dossier)}
            for position, name in enumerate(candidates, 1)]


def _presentation_title(value: str, position: int) -> str:
    """Produce rótulos de presentación españoles sin alterar el hecho fuente."""
    normalized = _slug(value)
    catalog = {
        "methodology": "Metodología",
        "technical-approach": "Enfoque técnico",
        "work-plan": "Plan de trabajo",
        "team": "Equipo",
        "project-team": "Equipo del proyecto",
        "scope": "Alcance",
        "deliverables": "Entregables",
        "methodological-principles": "Principios metodológicos",
        "activity-organisation": "Organización de las actividades",
        "validation-and-quality-control": "Validación y control de calidad",
    }
    # El dossier ya cruza la frontera de traducción. Solo se conservan alias
    # ingleses explícitos de planes históricos; el idioma declarado del pliego
    # nunca decide si un campo semántico válido se altera.
    return catalog.get(normalized, value)


def _contextual_purpose(title: str, dossier: dict, language: str = "es") -> str:
    context = dossier.get("contexto")
    base = f"Explicar de forma verificable cómo este apartado responde a «{title}» dentro del alcance licitado."
    if context:
        return base + " Relaciónelo con las necesidades y condicionantes descritos en el expediente, sin convertir hipótesis empresariales en compromisos."
    return base + " Distinga los hechos extraídos del pliego de las decisiones que deba aportar la empresa."


def _guidance(title, description, dossier, score, page_limit, requirements, criteria, evidence_fields,
              direct_evidence, language) -> dict:
    rules = dossier.get("memoria_tecnica", {}).get("reglas", [])
    avoid = [r["descripcion"] for r in rules if r.get("tipo") in ("prohibicion", "advertencia")]
    lowered = title.casefold()
    available = _relevant_information(lowered, dossier)
    questions = _guidance_questions(lowered, language)
    suffix = " Debe separar los hechos acreditados del expediente de las decisiones de la empresa pendientes de confirmar."
    intent = f"Orientación editorial: facilite la evaluación de {title.casefold()} mediante una respuesta verificable; no añade obligaciones distintas de las extraídas del pliego."
    return {"purpose": (description or _contextual_purpose(title, dossier, language)) + suffix,
            "evaluation_intent": intent,
            "questions_to_answer": questions,
            "mandatory_content": requirements, "criteria": criteria, "available_information": available,
            "company_inputs_required": ["Validar decisiones, recursos y compromisos que no consten en el expediente."],
            "evidence_summary": _evidence_summary(dossier, evidence_fields, direct_evidence), "avoid": avoid, "target_pages": page_limit,
            "target_words": _target_words(score, page_limit), "score": score, "score_confirmed": score is not None}


def _resolve_score(section_score, criteria: list[str], dossier: dict) -> dict:
    if section_score is not None:
        return {"score": section_score, "score_source": "tender_section", "score_confirmed": True, "score_criteria": []}
    matched = [item for item in dossier.get("criterios_adjudicacion", []) if item.get("nombre") in criteria and item.get("puntuacion_maxima") is not None]
    if len(matched) == 1:
        return {"score": matched[0]["puntuacion_maxima"], "score_source": "criterion", "score_confirmed": True, "score_criteria": [matched[0]["nombre"]]}
    if len(matched) > 1 and len(matched) == len(criteria):
        return {"score": sum(item["puntuacion_maxima"] for item in matched), "score_source": "criteria_sum", "score_confirmed": True, "score_criteria": [item["nombre"] for item in matched]}
    return {"score": None, "score_source": "unknown", "score_confirmed": False, "score_criteria": []}


def _relevant_information(title: str, dossier: dict) -> list[str]:
    if any(x in title for x in ("plan", "fase", "entregable", "hito")):
        return [x for phase in dossier.get("fases", []) for x in (phase.get("nombre"), phase.get("descripcion")) if x] + [x.get("nombre") for x in dossier.get("entregables_contrato", []) if x.get("nombre")]
    if any(x in title for x in ("equipo", "perfil")):
        return [" — ".join(filter(None, (x.get("nombre"), x.get("descripcion")))) for x in dossier.get("equipo", [])]
    if any(x in title for x in ("arquitect", "solución", "tecnolog")):
        return dossier.get("tecnologias", []) + dossier.get("trabajos", [])
    if any(x in title for x in ("alcance", "funcional", "comprensi", "diseño")):
        return ([dossier["contexto"]] if dossier.get("contexto") else []) + dossier.get("alcance", []) + dossier.get("objetivos", [])
    return dossier.get("trabajos", [])[:3]


def _guidance_questions(title: str, language: str) -> list[str]:
    if any(x in title for x in ("metodolog",)):
        return ["¿Cómo se organizarán las actividades?", "¿Qué mecanismos de validación se utilizarán?", "¿Cómo se controlarán calidad, riesgos y cambios?"]
    if any(x in title for x in ("plan", "fase", "entregable", "hito")):
        return ["¿Cuáles son las fases, dependencias e hitos?", "¿Qué entregables se producen en cada fase?", "¿Cómo se realizará el seguimiento?"]
    if any(x in title for x in ("equipo", "perfil")):
        return ["¿Qué perfiles exige el pliego?", "¿Qué responsabilidades tendrá cada perfil?", "¿Qué disponibilidad debe confirmar la empresa?"]
    if any(x in title for x in ("alcance", "funcional", "comprensi", "diseño")):
        return ["¿Qué procesos, usuarios y sistemas están dentro del alcance?", "¿Qué elementos quedan fuera?", "¿Qué restricciones condicionan la solución?"]
    return [f"¿Qué debe demostrarse en {title}?", "¿Qué evidencia del expediente respalda la respuesta?", "¿Qué decisión debe aportar la empresa?"]


def _evidence_summary(dossier: dict, fields: list[str], direct: list[dict]) -> list[dict]:
    items = list(direct) + [item for item in dossier.get("evidencias", []) if item.get("campo") in fields]
    result = [{"field": item.get("campo"), "document_id": item.get("documento_id"), "page": item.get("pagina"), "quoted_text": item.get("texto_citado")} for item in items]
    return list({(x["field"], x["document_id"], str(x["page"]), x["quoted_text"]): x for x in result}.values())


def _matching_requirements(title: str, dossier: dict) -> list[str]:
    normalized = _tokens(title)
    matches = []
    for item in dossier.get("requisitos_oferta", []):
        location = item.get("donde_responder") or ""
        description = item.get("descripcion") or ""
        if normalized & _tokens(location) or len(normalized & _tokens(description)) >= 2:
            matches.append(description)
    return matches


def _matching_criteria(title: str, dossier: dict) -> list[str]:
    normalized = _tokens(title)
    matches = []
    for item in dossier.get("criterios_adjudicacion", []):
        location = item.get("donde_responder") or ""
        name = item.get("nombre") or ""
        # "Memoria técnica" es un destino genérico y no asigna un criterio a
        # todos los apartados. Exigimos coincidencia sustantiva.
        if (len(normalized & _tokens(location)) >= 2
                or len(normalized & _tokens(name)) >= 2
                or _slug(name) == _slug(title)):
            matches.append(name)
    return matches


def _section_evidence_fields(item: dict, dossier: dict) -> list[str]:
    fields = [evidence.get("campo") for evidence in item.get("evidencias", [])
              if evidence.get("campo")]
    fields.extend(_matching_evidence_fields(item["titulo"], dossier))
    return list(dict.fromkeys(fields))


def _matching_evidence_fields(title: str, dossier: dict) -> list[str]:
    title_tokens = _tokens(title)
    fields = []
    for evidence in dossier.get("evidencias", []):
        field = evidence.get("campo") or ""
        if len(title_tokens & _tokens(field)) >= 2:
            fields.append(field)
    return list(dict.fromkeys(fields))


def _target_words(score: float | None, page_limit: float | None) -> int:
    if page_limit:
        return max(150, int(page_limit * 425))
    if score:
        return max(300, min(1500, int(score * 60)))
    return 500


def display_title(title: str, score: float | int | None, language: str = "es") -> str:
    """Presentación; el título canónico nunca se altera para validación."""
    if score is None:
        return title
    numeric = float(score)
    rendered = str(int(numeric)) if numeric.is_integer() else str(numeric).replace(".", ",")
    unit = "punto" if numeric == 1 else "puntos"
    return f"{title} ({rendered} {unit})"


def _apply_global_word_budget(sections: list[dict], max_pages: int | None) -> dict:
    if not max_pages:
        return {"mode": "unbounded", "estimated_words_per_page": 350, "total_target_words": sum(item["target_words"] for item in sections)}
    # Estimación deliberadamente conservadora: tablas, títulos e imágenes reducen
    # mucho la densidad frente a una página de texto continuo.
    total = max_pages * 350
    weights = [float(item.get("score") or 1) for item in sections]
    weight_total = sum(weights) or 1
    minimum = min(100, max(1, total // max(1, len(sections))))
    distributable = max(0, total - minimum * len(sections))
    allocated_extra = 0
    for index, (section, weight) in enumerate(zip(sections, weights)):
        extra = (distributable - allocated_extra if index == len(sections) - 1
                 else round(distributable * weight / weight_total))
        extra = max(0, min(extra, distributable - allocated_extra))
        target = minimum + extra
        if section.get("page_limit"):
            target = min(target, int(section["page_limit"] * 350))
        section["target_words"] = max(1, target)
        allocated_extra += extra
    return {"mode": "estimated", "estimated_words_per_page": 350,
            "total_target_words": sum(item["target_words"] for item in sections),
            "page_limit": max_pages}


def _constraint_pending(memory: dict) -> list[str]:
    if not memory:
        return ["No existe extracción estructurada de las restricciones de la memoria técnica."]
    pending = []
    formatting = memory.get("formato") or {}
    if formatting.get("paginas_maximas") is None:
        pending.append("No se ha localizado un límite global de páginas.")
    if memory.get("portada_computa_limite") is None:
        pending.append("No consta si la portada computa en el límite de páginas.")
    if memory.get("indice_computa_limite") is None:
        pending.append("No consta si el índice computa en el límite de páginas.")
    return pending


def _empty_format() -> dict:
    return {key: None for key in (
        "paginas_maximas", "fuente", "tamano_pt", "interlineado",
        "margen_superior_cm", "margen_inferior_cm", "margen_izquierdo_cm",
        "margen_derecho_cm",
    )}


def _slug(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")[:48] or "section"


def _tokens(value: str) -> set[str]:
    # Términos de rótulo que se repiten en varios criterios del mismo pliego no
    # son suficientes para asignarlos a un apartado concreto.
    ignored = {"de", "del", "la", "las", "el", "los", "y", "en", "para", "a",
               "memoria", "propuesta", "tecnica", "funcional", "fase", "caso"}
    return {part for part in _slug(value).split("-") if len(part) > 2 and part not in ignored}
