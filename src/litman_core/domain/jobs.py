from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class JobType(StrEnum):
    ASSESSMENT = "assessment"
    DETAILED_ANALYSIS = "detailed-analysis"


class StorageKind(StrEnum):
    LOCAL = "local"
    GOOGLE_DRIVE = "google-drive"


@dataclass(frozen=True)
class JobRequest:
    job_id: str
    job_type: JobType
    input_kind: StorageKind
    input_location: str
    output_directory: Path
    google_drive_folder_id: str | None = None
    include_run_files: bool = False
    codex_model: str | None = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MaterializedCase:
    case_id: str
    directory: Path
    source_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class PublishedArtifact:
    name: str
    uri: str
    checksum: str


@dataclass(frozen=True)
class JobResult:
    job_id: str
    job_type: JobType
    status: str
    publication_id: str
    local_path: str
    artifacts: tuple[PublishedArtifact, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)
