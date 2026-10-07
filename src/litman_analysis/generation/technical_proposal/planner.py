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

SUPPORTED_LANGUAGES = ("es", "en")


def build_document_plan(dossier: dict, template_id: str = "next-standard-v1") -> dict:
    memory = dossier.get("memoria_tecnica") or {}
    specified = sorted(memory.get("secciones") or [], key=lambda item: item.get("orden", 0))
    structure_source = "tender" if specified else "detailed-analysis-suggestion"
    if specified:
        sections = [_specified_section(item, dossier, index) for index, item in enumerate(specified, 1)]
    else:
        suggested = [title for title in dossier.get("estructura_documento_tecnico", []) if title]
        titles = suggested or list(DEFAULT_SECTION_TITLES)
        structure_source = "detailed-analysis-suggestion" if suggested else "fallback"
        sections = [_fallback_section(title, dossier, index) for index, title in enumerate(titles, 1)]

    formatting = memory.get("formato") or _empty_format()
    word_budget = _apply_global_word_budget(sections, formatting.get("paginas_maximas"))
    pending = _constraint_pending(memory)
    return {
        "version": "document-plan-v1",
        "template_id": template_id,
        "document_title": memory.get("nombre_documento") or "Memoria técnica",
        "language": normalize_output_language(memory.get("idioma")),
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
    """Convierte el idioma libre del pliego en una variante renderizable.

    Cuando el expediente permite varios idiomas, español es el desempate
    acordado. Por ahora la interfaz visual solo dispone de español e inglés.
    """
    if not value:
        return "es"
    normalized = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().lower()
    spanish = any(term in normalized for term in ("espanol", "castellano", "spanish"))
    english = any(term in normalized for term in ("ingles", "english"))
    if spanish:
        return "es"
    if english:
        return "en"
    if normalized.strip() in SUPPORTED_LANGUAGES:
        return normalized.strip()
    return "es"


def _specified_section(item: dict, dossier: dict, index: int) -> dict:
    score = item.get("puntuacion")
    page_limit = item.get("limite_paginas")
    return {
        "id": f"section-{index:03d}-{_slug(item['titulo'])}",
        "order": index,
        "title": item["titulo"],
        "purpose": item.get("descripcion") or "Responder al apartado exigido por el pliego.",
        "required": item.get("obligatoria") is not False,
        "score": score,
        "page_limit": page_limit,
        "target_words": _target_words(score, page_limit),
        "requirements": item.get("requisitos_relacionados") or _matching_requirements(item["titulo"], dossier),
        "criteria": _matching_criteria(item["titulo"], dossier),
        "evidence_fields": _section_evidence_fields(item, dossier),
        "generation_status": "ready",
    }


def _fallback_section(title: str, dossier: dict, index: int) -> dict:
    return {
        "id": f"section-{index:03d}-{_slug(title)}",
        "order": index,
        "title": title,
        "purpose": "Estructura propuesta al no haberse localizado un índice obligatorio en el expediente.",
        "required": True,
        "score": None,
        "page_limit": None,
        "target_words": 500,
        "requirements": _matching_requirements(title, dossier),
        "criteria": _matching_criteria(title, dossier),
        "evidence_fields": _matching_evidence_fields(title, dossier),
        "generation_status": "ready",
    }


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
