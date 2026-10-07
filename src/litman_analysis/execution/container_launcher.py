"""Host adapter that launches exactly one container for a public job."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from urllib.parse import unquote, urlparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from litman_analysis.domain.jobs import JobRequest, JobType, StorageKind


@dataclass(frozen=True)
class ContainerLaunchResult:
    payload: dict[str, Any]


class ContainerJobLauncher:
    def __init__(self, *, project_root: Path | None = None,
                 runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> None:
        self.project_root = (project_root or Path(__file__).resolve().parents[3]).resolve()
        self.runner = runner

    def run(self, job: JobRequest) -> ContainerLaunchResult:
        self._validate(job)
        state_root = self.project_root / ".local-state" / "launcher"
        state_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f"{job.job_id}-", dir=state_root) as temporary:
            execution = Path(temporary)
            job_dir, placeholder_input, placeholder_output = (
                execution / "job", execution / "unused-input", execution / "unused-output")
            for path in (job_dir, placeholder_input, placeholder_output):
                path.mkdir()
            input_dir = (Path(job.input_location).expanduser().resolve()
                         if job.input_kind is StorageKind.LOCAL else placeholder_input)
            output_dir = (Path(job.output_location).expanduser().resolve()
                          if job.output_kind is StorageKind.LOCAL else placeholder_output)
            if job.output_kind is StorageKind.LOCAL:
                output_dir.mkdir(parents=True, exist_ok=True)
                self._require_directory(output_dir, "directorio local de salida", writable=True)
            if job.input_kind is StorageKind.LOCAL:
                self._require_directory(input_dir, "directorio local de entrada", readable=True)
            internal = self._internal_contract(job)
            (job_dir / "job.json").write_text(
                json.dumps(internal, ensure_ascii=False, indent=2), encoding="utf-8")
            env = os.environ.copy()
            env.update({
                "LITMAN_ANALYSIS_JOB_DIR": str(job_dir.resolve()),
                "LITMAN_ANALYSIS_INPUT_DIR": str(input_dir),
                "LITMAN_ANALYSIS_OUTPUT_DIR": str(output_dir),
                "LITMAN_ANALYSIS_RUNS_HOST_DIR": str(self._host_path("LITMAN_ANALYSIS_RUNS_HOST_DIR", "runs")),
                "LITMAN_ANALYSIS_SECRETS_DIR": str(self._host_path("LITMAN_ANALYSIS_SECRETS_DIR", "local-secrets")),
                "LITMAN_ANALYSIS_CODEX_STATE_DIR": str(self._host_path("LITMAN_ANALYSIS_CODEX_STATE_DIR", ".local-state/codex")),
            })
            for name in ("LITMAN_ANALYSIS_RUNS_HOST_DIR", "LITMAN_ANALYSIS_SECRETS_DIR", "LITMAN_ANALYSIS_CODEX_STATE_DIR"):
                Path(env[name]).mkdir(parents=True, exist_ok=True)
            completed = self.runner(
                ["docker", "compose", "run", "--rm", "litman-analysis", "run", "/job/job.json"],
                cwd=self.project_root, env=env, text=True, stdout=subprocess.PIPE,
                stderr=None, check=False,
            )
            if completed.returncode:
                raise subprocess.CalledProcessError(completed.returncode, completed.args)
            try:
                payload = json.loads(completed.stdout)
            except (TypeError, json.JSONDecodeError) as exc:
                raise RuntimeError("El contenedor no devolvió un resultado JSON válido") from exc
            return ContainerLaunchResult(self._host_payload(
                payload, output_dir=output_dir,
                runs_dir=Path(env["LITMAN_ANALYSIS_RUNS_HOST_DIR"]),
            ))

    def _host_path(self, variable: str, default: str) -> Path:
        return Path(os.environ.get(variable, self.project_root / default)).expanduser().resolve()

    @staticmethod
    def _require_directory(path: Path, label: str, *, readable: bool = False,
                           writable: bool = False) -> None:
        mode = os.X_OK | (os.R_OK if readable else 0) | (os.W_OK if writable else 0)
        if not path.is_dir() or not os.access(path, mode):
            qualifier = "legible" if readable else "escribible"
            raise ValueError(f"El {label} no es {qualifier}: {path}")

    @staticmethod
    def _host_payload(payload: dict[str, Any], *, output_dir: Path,
                      runs_dir: Path) -> dict[str, Any]:
        translated = dict(payload)
        for key in ("run_dir", "diagnostics_dir", "execution_dir"):
            value = translated.get(key)
            if isinstance(value, str) and (value == "/data/runs" or value.startswith("/data/runs/")):
                translated[key] = str(runs_dir / Path(value).relative_to("/data/runs"))
        artifacts = translated.get("artifacts")
        if isinstance(artifacts, list):
            translated["artifacts"] = [
                ContainerJobLauncher._host_artifact(item, output_dir) for item in artifacts
            ]
        return translated

    @staticmethod
    def _host_artifact(item: Any, output_dir: Path) -> Any:
        if not isinstance(item, dict):
            return item
        translated = dict(item)
        uri = translated.get("uri")
        if isinstance(uri, str):
            parsed = urlparse(uri)
            path = Path(unquote(parsed.path)) if parsed.scheme == "file" else None
            if path is not None and (path == Path("/output") or Path("/output") in path.parents):
                translated["uri"] = (output_dir / path.relative_to("/output")).as_uri()
        return translated

    @staticmethod
    def _internal_contract(job: JobRequest) -> dict[str, Any]:
        return {
            "job_id": job.job_id, "job_type": job.job_type.value,
            "input": {"kind": job.input_kind.value,
                      "location": "/input" if job.input_kind is StorageKind.LOCAL else job.input_location},
            "output": {"kind": job.output_kind.value,
                       "location": "/output" if job.output_kind is StorageKind.LOCAL else job.output_location},
            "options": job.options,
        }

    @staticmethod
    def _validate(job: JobRequest) -> None:
        if job.job_type not in {JobType.ASSESSMENT, JobType.DETAILED_ANALYSIS}:
            raise ValueError("Tipo de job no soportado")
        supported = {(source, destination)
                     for source in StorageKind for destination in StorageKind}
        if (job.input_kind, job.output_kind) not in supported:
            raise ValueError("Combinación de almacenamiento no soportada")
        if job.input_kind is StorageKind.LOCAL and not Path(job.input_location).expanduser().resolve().is_dir():
            raise ValueError(f"No existe el directorio local de entrada: {job.input_location}")
