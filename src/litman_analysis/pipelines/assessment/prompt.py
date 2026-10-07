from __future__ import annotations

import json
from pathlib import Path

import yaml

from litman_analysis.domain.documents import Document, NormalizedDocument


def load_prompts(prompt_dir: Path, config_path: Path) -> tuple[str, str, str, dict]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return (
        (prompt_dir / "system.md").read_text(encoding="utf-8"),
        (prompt_dir / "extraction.md").read_text(encoding="utf-8"),
        (prompt_dir / "VERSION").read_text(encoding="utf-8").strip(),
        config,
    )


def build_prompt(task: str, documents: list[Document], normalized: list[NormalizedDocument],
                 extraction_config: dict) -> str:
    normalized_by_id = {item.document_id: item for item in normalized}
    manifest = [{
        "documento_id": doc.document_id, "nombre": doc.filename,
        "ruta_relativa": doc.relative_path, "mime": doc.mime_type,
        "tipo_estimado": doc.type_hint, "fase_estimada": doc.phase_hint,
        "estado": doc.status, "motivo": doc.status_reason,
        "normalizacion": normalized_by_id[doc.document_id].public_dict(),
    } for doc in documents]
    references = []
    for doc in documents:
        item = normalized_by_id[doc.document_id]
        references.append({
            "documento_id": doc.document_id,
            "archivo_original": str(doc.path),
            "archivo_markdown": item.normalized_path,
            "nombre": doc.filename,
            "tipo_estimado": doc.type_hint,
            "fase_estimada": doc.phase_hint,
            "paginas": item.page_count,
            "caracteres": item.character_count,
            "estado": item.status,
            "advertencias": item.warnings,
        })
    extraction = extraction_config.get("extraction", {})
    definitions = extraction.get("definiciones", {})
    instructions = extraction.get("instrucciones", [])
    config_section = (
        "\n# Configuración de extracción\n"
        "## Campos críticos\n" + "\n".join(f"- {field}" for field in extraction.get("campos_criticos", [])) +
        "\n## Definiciones\n" + "\n".join(f"- {key}: {value}" for key, value in definitions.items()) +
        "\n## Instrucciones específicas\n" + "\n".join(f"- {item}" for item in instructions)
    )
    return (
        f"{task}\n\n# Inventario documental\n"
        f"{json.dumps(manifest, ensure_ascii=False, indent=2)}\n"
        f"{config_section}\n"
        "\n# Referencias documentales (contenido no incluido en este prompt)\n"
        f"{json.dumps(references, ensure_ascii=False, indent=2)}\n\n"
        "Los archivos Markdown son la fuente normalizada completa. Debes abrirlos "
        "con las herramientas del entorno y leerlos antes de responder. No bases "
        "el análisis únicamente en nombres, metadatos o resúmenes."
    )
