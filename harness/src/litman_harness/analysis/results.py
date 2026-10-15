"""Validation of Core's public CLI result and the closed public artifact catalogue.

The harness depends only on Core's public contract: the exit code of
``litman-core run`` and its stdout JSON (``status``, ``publication_id``,
``local_path`` and ``artifacts[{name, uri, checksum}]`` with SHA-256 checksums).
With ``include_run_files = false`` ``local_path`` holds exactly the public files,
flat.  No internal Core file (validation, manifests, structured output) is read.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..errors import HarnessError
from .inputs import sha256_file

TECHNICAL_DOCUMENT_ID = "technical-document"
_FIXED_CATALOG = {
    "assessment": ("ficha_oportunidad.pdf",),
    "detailed-analysis": ("resumen_tecnico.docx", "guia_preparacion_oferta.docx", "simulador_economico.xlsx"),
}
ROLES = {"ficha_oportunidad.pdf": "opportunity_report", "resumen_tecnico.docx": "technical_summary",
         "guia_preparacion_oferta.docx": "bid_preparation_guide", "simulador_economico.xlsx": "economic_simulator"}
MIME_TYPES = {".pdf": "application/pdf",
              ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
              ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def public_catalog(job_type: str) -> list[str]:
    """Fixed public names; a detailed run adds exactly one more DOCX, the technical document."""
    return list(_FIXED_CATALOG[job_type])


def includes_technical_document(job_type: str) -> bool:
    return job_type == "detailed-analysis"


def _invalid(message: str, **details: Any) -> HarnessError:
    return HarnessError("invalid_core_result", message, details=details)


def validate_public_result(payload: dict[str, Any], run_dir: Path, job_type: str) -> list[dict[str, Any]]:
    """Check the declared artifacts against the closed catalogue and the files on disk.

    Returns name, role, MIME type, local path and SHA-256 of each public artifact.
    """
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not all(
            isinstance(item, dict) and isinstance(item.get("name"), str) and isinstance(item.get("checksum"), str)
            for item in artifacts):
        raise _invalid("Core no declaró la lista de artefactos públicos")
    declared = {item["name"]: item["checksum"] for item in artifacts}
    if len(declared) != len(artifacts) or any(Path(name).name != name for name in declared):
        raise _invalid("Core declaró artefactos duplicados o con ruta", names=sorted(declared))
    fixed = set(_FIXED_CATALOG[job_type])
    extra = sorted(set(declared) - fixed)
    if includes_technical_document(job_type):
        technical = [name for name in extra if name.lower().endswith(".docx")]
        if len(technical) != 1:
            raise _invalid("Core debe declarar exactamente un DOCX técnico", candidates=technical)
        extra.remove(technical[0])
    missing = sorted(fixed - set(declared))
    if missing or extra:
        raise _invalid("Los artefactos de Core no coinciden con el catálogo público", missing=missing, extra=extra)
    result = []
    order = list(_FIXED_CATALOG[job_type])
    for name in sorted(declared, key=lambda item: order.index(item) if item in order else len(order)):
        path = run_dir / name
        if not path.is_file():
            raise _invalid("Falta un artefacto público declarado por Core", name=name)
        checksum = sha256_file(path)
        if checksum != declared[name]:
            raise _invalid("El SHA-256 de un artefacto no coincide con el declarado por Core", name=name)
        result.append({"name": name, "role": ROLES.get(name, TECHNICAL_DOCUMENT_ID),
                       "mime_type": MIME_TYPES[path.suffix.lower()], "path": str(path), "sha256": checksum})
    return result
