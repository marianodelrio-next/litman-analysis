from __future__ import annotations

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator
import yaml

from litman_analysis.domain.jobs import JobRequest, JobType, StorageKind
from litman_analysis.resource_paths import resource_path

_JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def load_job(path: Path) -> JobRequest:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
    elif path.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        raise ValueError("El job debe tener extensión .json, .yaml o .yml")
    if not isinstance(data, dict):
        raise ValueError("El job debe ser un objeto JSON o YAML")
    schema_path = resource_path("schemas", "job.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda error: list(error.path))
    if errors:
        details = "; ".join(
            f"{'.'.join(map(str, error.path)) or 'root'}: {error.message}" for error in errors)
        raise ValueError(f"Contrato de job inválido: {details}")
    missing = sorted({"job_id", "job_type", "input", "output"} - data.keys())
    if missing:
        raise ValueError(f"Faltan campos del job: {', '.join(missing)}")
    job_id = data["job_id"]
    if not isinstance(job_id, str) or not _JOB_ID.fullmatch(job_id):
        raise ValueError("job_id contiene caracteres no permitidos")
    input_data, output_data = data["input"], data["output"]
    if not isinstance(input_data, dict) or not isinstance(output_data, dict):
        raise ValueError("input y output deben ser objetos")
    options = data.get("options", {})
    if not isinstance(options, dict):
        raise ValueError("options debe ser un objeto")
    return JobRequest(
        job_id=job_id, job_type=JobType(data["job_type"]),
        input_kind=StorageKind(input_data["kind"]), output_kind=StorageKind(output_data["kind"]),
        input_location=input_data["location"], output_location=output_data["location"],
        options=options,
    )
