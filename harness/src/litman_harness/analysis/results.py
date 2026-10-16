"""Validation of Core's public CLI result and the closed public artifact catalogue.

The harness depends only on Core's public contract: the exit code of
``litman-core run`` and its stdout JSON (``status``, ``publication_id``,
``local_path`` and ``artifacts[{role, name, uri, checksum}]`` with SHA-256
checksums). With ``include_run_files = false`` ``local_path`` holds exactly
the public files, flat.  No internal Core file (validation, manifests,
structured output) is read. Validation is by ``role``, the closed contract
in ``docs/contracts.md``, never by file name.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..errors import HarnessError
from .inputs import sha256_file

TECHNICAL_DOCUMENT_ID = "technical_document"
REQUIRED_ROLES = {
    "assessment": ("opportunity_report",),
    "detailed-analysis": ("technical_summary", "bid_preparation_guide", TECHNICAL_DOCUMENT_ID, "economic_simulator"),
}
MIME_TYPES = {".pdf": "application/pdf",
              ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
              ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def includes_technical_document(job_type: str) -> bool:
    return TECHNICAL_DOCUMENT_ID in REQUIRED_ROLES[job_type]


def _invalid(message: str, **details: Any) -> HarnessError:
    return HarnessError("invalid_core_result", message, details=details)


def validate_public_result(payload: dict[str, Any], run_dir: Path, job_type: str) -> list[dict[str, Any]]:
    """Check the declared artifacts against the closed set of required roles and the files on disk.

    Returns name, role, MIME type, local path and SHA-256 of each public artifact,
    ordered by ``REQUIRED_ROLES[job_type]``.
    """
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not all(
            isinstance(item, dict) and isinstance(item.get("role"), str)
            and isinstance(item.get("name"), str) and isinstance(item.get("checksum"), str)
            for item in artifacts):
        raise _invalid("Core no declaró la lista de artefactos públicos")
    required = REQUIRED_ROLES[job_type]
    by_role: dict[str, dict[str, str]] = {}
    for item in artifacts:
        role, name = item["role"], item["name"]
        if Path(name).name != name:
            raise _invalid("Core declaró un artefacto con ruta", name=name)
        if role not in required:
            raise _invalid("Core declaró un rol de artefacto desconocido o no esperado", role=role)
        if role in by_role:
            raise _invalid("Core declaró el mismo rol más de una vez", role=role)
        by_role[role] = {"name": name, "checksum": item["checksum"]}
    missing = sorted(set(required) - set(by_role))
    if missing:
        raise _invalid("Faltan roles obligatorios en los artefactos de Core", missing=missing)
    result = []
    for role in required:
        name, checksum = by_role[role]["name"], by_role[role]["checksum"]
        path = run_dir / name
        if not path.is_file():
            raise _invalid("Falta un artefacto público declarado por Core", name=name)
        actual = sha256_file(path)
        if actual != checksum:
            raise _invalid("El SHA-256 de un artefacto no coincide con el declarado por Core", name=name)
        result.append({"name": name, "role": role, "mime_type": MIME_TYPES[path.suffix.lower()], "path": str(path), "sha256": actual})
    return result
