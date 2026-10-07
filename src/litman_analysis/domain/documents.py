from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Document:
    document_id: str
    path: Path
    relative_path: str
    filename: str
    suffix: str
    mime_type: str
    size_bytes: int
    sha256: str
    type_hint: str
    phase_hint: str
    status: str
    status_reason: str | None = None

    def public_dict(self) -> dict:
        data = asdict(self)
        data["path"] = str(self.path)
        return data


@dataclass(frozen=True)
class NormalizedDocument:
    document_id: str
    normalized_path: str | None
    status: str
    method: str | None
    page_count: int | None
    character_count: int
    warnings: list[str]

    def public_dict(self) -> dict:
        return asdict(self)
