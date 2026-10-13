"""Typed loader for the single public config.toml contract."""
from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

from litman_core.domain.jobs import JobRequest, JobType, StorageKind
from litman_core.generation_config import merge_generation

_ROOT = {"job", "input", "output", "codex", "publication", "analysis"}


def load_job(path: Path) -> JobRequest:
    path = path.expanduser().resolve()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"No existe la configuración: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"TOML inválido: {exc}") from exc
    _keys(data, _ROOT, "root")
    job, input_data, output = (_table(data, name) for name in ("job", "input", "output"))
    _keys(job, {"id", "type"}, "job"); _keys(input_data, {"kind", "location"}, "input"); _keys(output, {"directory", "google_drive_folder_id"}, "output")
    job_id = _text(job, "id", "job.id")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", job_id):
        raise ValueError("job.id contiene caracteres no permitidos")
    job_type = _enum(_text(job, "type", "job.type"), JobType, "job.type")
    input_kind = _enum(_text(input_data, "kind", "input.kind"), StorageKind, "input.kind")
    location = _text(input_data, "location", "input.location")
    if input_kind is StorageKind.LOCAL:
        location = str((path.parent / location).resolve()) if not Path(location).is_absolute() else str(Path(location).resolve())
    directory = Path(_text(output, "directory", "output.directory"))
    output_directory = (path.parent / directory).resolve() if not directory.is_absolute() else directory.resolve()
    drive_id = output.get("google_drive_folder_id")
    if drive_id is not None and (not isinstance(drive_id, str) or not drive_id):
        raise ValueError("output.google_drive_folder_id debe ser texto no vacío")
    codex = data.get("codex", {})
    if not isinstance(codex, dict): raise ValueError("codex debe ser una tabla")
    _keys(codex, {"model"}, "codex")
    model = codex.get("model")
    if model is not None and not isinstance(model, str): raise ValueError("codex.model debe ser texto")
    publication = data.get("publication", {})
    if not isinstance(publication, dict): raise ValueError("publication debe ser una tabla")
    _keys(publication, {"include_run_files"}, "publication")
    include = publication.get("include_run_files", False)
    if type(include) is not bool: raise ValueError("publication.include_run_files debe ser booleano")
    generation = _generation(data, job_type)
    return JobRequest(job_id, job_type, input_kind, location, output_directory, drive_id, include, model, {"generation": generation} if generation else {})


def _generation(data: dict[str, Any], job_type: JobType) -> dict[str, Any] | None:
    analysis = data.get("analysis", {})
    if not isinstance(analysis, dict): raise ValueError("analysis debe ser una tabla")
    _keys(analysis, {"detailed"}, "analysis")
    detailed = analysis.get("detailed", {})
    if not isinstance(detailed, dict): raise ValueError("analysis.detailed debe ser una tabla")
    _keys(detailed, {"generation"}, "analysis.detailed")
    generation = detailed.get("generation", {})
    if not isinstance(generation, dict): raise ValueError("analysis.detailed.generation debe ser una tabla")
    return merge_generation(generation) if job_type is JobType.DETAILED_ANALYSIS else None


def _table(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name)
    if not isinstance(value, dict): raise ValueError(f"{name} debe ser una tabla")
    return value


def _keys(value: dict[str, Any], allowed: set[str], path: str) -> None:
    for key in value:
        if key not in allowed:
            raise ValueError(f"Clave TOML desconocida: {key if path == 'root' else path + '.' + key}")


def _text(data: dict[str, Any], key: str, path: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value: raise ValueError(f"{path} debe ser texto no vacío")
    return value


def _enum(value: str, enum: type, path: str):
    try: return enum(value)
    except ValueError as exc: raise ValueError(f"{path} tiene un valor no admitido") from exc
