from __future__ import annotations

import json
from pathlib import Path

import yaml

from litman_analysis.domain.documents import Document, NormalizedDocument


def load_prompts(prompt_dir: Path, config_path: Path) -> tuple[str, str, str, dict]:
    return (
        (prompt_dir / "system.md").read_text(encoding="utf-8"),
        (prompt_dir / "extraction.md").read_text(encoding="utf-8"),
        (prompt_dir / "VERSION").read_text(encoding="utf-8").strip(),
        yaml.safe_load(config_path.read_text(encoding="utf-8")),
    )


def build_prompt(task: str, documents: list[Document], normalized: list[NormalizedDocument], config: dict,
                 assessment_result: dict | None = None) -> str:
    normalized_by_id = {item.document_id: item for item in normalized}
    references = [{
        "documento_id": doc.document_id, "nombre": doc.filename,
        "archivo_markdown": normalized_by_id[doc.document_id].normalized_path,
        "estado": normalized_by_id[doc.document_id].status,
        "paginas": normalized_by_id[doc.document_id].page_count,
        "advertencias": normalized_by_id[doc.document_id].warnings,
    } for doc in documents]
    extraction = config.get("extraction", {})
    instructions = "\n".join(f"- {item}" for item in extraction.get("pendientes", []))
    assessment_context = ""
    if assessment_result:
        assessment_context = "\n# Resultado de análisis inicial\n" + json.dumps({
            "ficha": assessment_result.get("extraction", {}).get("ficha", {}),
            "decision": assessment_result.get("decision", {}),
        }, ensure_ascii=False, indent=2) + "\n"
    return (
        f"{task}\n\n# Objetivos\n" + "\n".join(f"- {item}" for item in extraction.get("objetivos", [])) +
        f"\n\n# Instrucciones sobre pendientes\n{instructions}\n"
        "\n# Documentos disponibles\n" + json.dumps(references, ensure_ascii=False, indent=2) +
        assessment_context + "\nAbre y revisa los archivos Markdown disponibles antes de responder. "
        "Usa sus marcadores de página para las evidencias."
    )
