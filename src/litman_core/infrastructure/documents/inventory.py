from __future__ import annotations

import hashlib
import mimetypes
import re
from pathlib import Path

from litman_core.domain.documents import Document


SUPPORTED_SUFFIXES = {".pdf", ".xml", ".txt", ".md", ".json", ".docx"}
IGNORED_NAMES = {"caso.yaml", "esperado.yaml"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _classify(filename: str) -> tuple[str, str]:
    name = filename.lower()
    rules = [
        (r"valoraci[oó]n|informe tecnico", "informe_valoracion", "valoracion"),
        (r"adjudic", "adjudicacion", "adjudicacion"),
        (r"formaliza", "formalizacion", "formalizacion"),
        (r"technicaldocument|prescripciones t[eé]cnicas|\bppt\b", "ppt", "licitacion"),
        (r"legaldocument|cl[aá]usulas administrativas|\bpcap\b", "pcap", "licitacion"),
        (r"anuncio|placsp", "anuncio_o_fuente", "licitacion"),
        (r"rectifica|correcci[oó]n|aclaraci[oó]n", "rectificacion", "licitacion"),
        (r"memoria justificativa|iniciaci[oó]n|aprobaci[oó]n", "preparatorio", "preparacion"),
        (r"anexo|modelo", "anexo_o_modelo", "licitacion"),
    ]
    for pattern, kind, phase in rules:
        if re.search(pattern, name):
            return kind, phase
    return "desconocido", "desconocida"


def inventory(case_dir: Path, max_file_mb: int = 25) -> list[Document]:
    case_dir = case_dir.resolve()
    if not case_dir.is_dir():
        raise ValueError(f"No existe la carpeta del caso: {case_dir}")

    documents: list[Document] = []
    max_bytes = max_file_mb * 1024 * 1024
    for path in sorted(case_dir.rglob("*")):
        if not path.is_file() or path.name in IGNORED_NAMES or path.name.startswith("."):
            continue
        suffix = path.suffix.lower()
        size = path.stat().st_size
        digest = _sha256(path)
        kind, phase = _classify(path.name)
        status, reason = "ready", None
        if suffix not in SUPPORTED_SUFFIXES:
            status, reason = "unsupported", f"Formato {suffix or 'sin extensión'} no soportado en v1"
        elif size > max_bytes:
            status, reason = "too_large", f"Supera el límite de {max_file_mb} MB"
        documents.append(Document(
            document_id=f"doc_{digest[:12]}", path=path,
            relative_path=str(path.relative_to(case_dir)), filename=path.name,
            suffix=suffix, mime_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            size_bytes=size, sha256=digest, type_hint=kind, phase_hint=phase,
            status=status, status_reason=reason,
        ))
    return documents
