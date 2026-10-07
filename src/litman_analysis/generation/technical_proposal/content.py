from __future__ import annotations

import json


def build_generation_prompt(task: str, dossier: dict, plan: dict) -> str:
    safe_dossier = {
        key: dossier.get(key) for key in (
            "schema_version", "cabecera", "contexto", "objetivos", "alcance", "trabajos", "fases",
            "entregables_contrato", "equipo", "tecnologias", "requisitos_oferta",
            "criterios_adjudicacion", "pendientes", "evidencias", "calidad",
            "memoria_tecnica",
        )
    }
    return (
        f"{task}\n\n# Plan del documento\n"
        + json.dumps(plan, ensure_ascii=False, indent=2)
        + "\n\n# Dossier validado\n"
        + json.dumps(safe_dossier, ensure_ascii=False, indent=2)
    )


def fallback_content(dossier: dict, plan: dict) -> dict:
    sections = []
    for section in plan["sections"]:
        entries = _entries_for_title(section["title"], dossier)
        blocks = []
        if entries:
            if len(entries) == 1:
                blocks.append(_block("paragraph", text=entries[0]))
            else:
                blocks.append(_block("bullet_list", items=entries))
        else:
            blocks.append(_block("pending", text="Completar y validar esta sección con el equipo responsable."))
        sections.append({
            "id": section["id"],
            "title": section["title"],
            "blocks": blocks,
            "requirements_covered": section["requirements"],
            "evidence_fields": [],
            "pending": [] if entries else ["Contenido específico pendiente de elaboración."],
            "review": {"required": True, "reason": "Borrador automático sin redacción LLM."},
        })
    pending = [{"section_id": None, "description": item, "reason": "Restricción no localizada"}
               for item in plan["pending_decisions"]]
    pending.extend(_technical_pending(dossier))
    return {"document_title": plan["document_title"], "language": plan["language"],
            "sections": sections, "pending": pending,
            "warnings": ["Contenido generado mediante fallback determinista; requiere redacción y revisión."]}


def skeleton_content(dossier: dict, plan: dict) -> dict:
    """Crea una guía breve y trazable, sin redactar contenido de oferta."""
    sections = []
    language = plan.get("language", "es")
    placeholder_title = "Example subsection" if language == "en" else "Ejemplo de subapartado"
    placeholder_text = (
        "[PLACEHOLDER] Replace this example with the necessary subsection and add its content."
        if language == "en" else
        "[PLACEHOLDER] Sustituya este ejemplo por el subapartado necesario y añada su contenido."
    )
    for section in plan["sections"]:
        guidance = []
        if section.get("purpose"):
            guidance.append(f"Finalidad: {section['purpose']}")
        guidance.extend(f"Requisito del pliego: {item}" for item in section.get("requirements", []))
        guidance.extend(f"Criterio de evaluación: {item}" for item in section.get("criteria", []))
        if section.get("score") is not None:
            guidance.append(f"Puntuación máxima: {section['score']}")
        if section.get("page_limit") is not None:
            guidance.append(f"Límite del apartado: {section['page_limit']} páginas")
        if not guidance:
            guidance.append("Revisar el pliego y concretar el objetivo de este apartado.")
        sections.append({
            "id": section["id"],
            "title": section["title"],
            "blocks": [
                _block("bullet_list", items=guidance),
                _block("subheading", text=placeholder_title,
                       block_id=f"{section['id']}-example-subsection", level=2),
                _block("paragraph", text=placeholder_text),
            ],
            "requirements_covered": [],
            "evidence_fields": [],
            "pending": ["Completar la respuesta de este apartado y validarla antes de presentar la oferta."],
            "review": {"required": True, "reason": "Documento esqueleto para cumplimentación humana."},
        })
    pending = [{"section_id": None, "description": item, "reason": "Restricción no resuelta"}
               for item in plan.get("pending_decisions", [])]
    pending.extend(_technical_pending(dossier))
    return {
        "document_title": plan["document_title"],
        "language": plan["language"],
        "sections": sections,
        "pending": pending,
        "warnings": ["Documento esqueleto: no contiene una propuesta técnica redactada."],
    }


def _entries_for_title(title: str, dossier: dict) -> list[str]:
    lowered = title.lower()
    if "resumen" in lowered or "context" in lowered or "situaci" in lowered:
        return [dossier["contexto"]] if dossier.get("contexto") else []
    if "objetiv" in lowered:
        return dossier.get("objetivos", [])
    if "alcance" in lowered:
        return dossier.get("alcance", [])
    if any(term in lowered for term in ("fase", "plan", "cronograma")):
        return [" — ".join(part for part in (item.get("nombre"), item.get("descripcion"), item.get("plazo")) if part)
                for item in dossier.get("fases", [])]
    if "entregable" in lowered or "hito" in lowered:
        return [" — ".join(part for part in (item.get("nombre"), item.get("descripcion")) if part)
                for item in dossier.get("entregables_contrato", [])]
    if "equipo" in lowered or "perfil" in lowered:
        return [" — ".join(part for part in (item.get("nombre"), item.get("descripcion")) if part)
                for item in dossier.get("equipo", [])]
    if "tecnolog" in lowered or "arquitect" in lowered:
        return dossier.get("tecnologias", [])
    return dossier.get("trabajos", [])


def _technical_pending(dossier: dict) -> list[dict]:
    """No arrastra al borrador del Sobre técnico decisiones de otros sobres."""
    return [
        {"section_id": None, "description": item.get("descripcion", "Pendiente"),
         "reason": item.get("motivo")}
        for item in dossier.get("pendientes", [])
        if item.get("destino") in ("documento_tecnico", "general")
    ]


def _block(block_type: str, *, text: str | None = None, items: list[str] | None = None,
           block_id: str | None = None, level: int | None = None) -> dict:
    block = {"type": block_type, "text": text, "items": items or [], "headers": [], "rows": []}
    if block_id is not None:
        block["id"] = block_id
    if level is not None:
        block["level"] = level
    return block
