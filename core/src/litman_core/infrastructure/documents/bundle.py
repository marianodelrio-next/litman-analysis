from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from litman_core.config import Settings
from litman_core.domain.documents import Document, NormalizedDocument

from .inventory import inventory
from .normalize import normalize_documents


@dataclass(frozen=True)
class DocumentBundle:
    case_dir: Path
    documents: list[Document]
    normalized: list[NormalizedDocument]


def prepare_bundle(case_dir: Path, output_dir: Path, settings: Settings) -> DocumentBundle:
    case_dir = case_dir.resolve()
    documents = inventory(case_dir, settings.max_file_mb)
    if not documents:
        raise ValueError(f"El caso no contiene documentos: {case_dir}")
    normalized = normalize_documents(documents, output_dir / "documents")
    return DocumentBundle(case_dir, documents, normalized)
