"""Local ``litman-core`` process boundary: explicit config.toml and execution.

The harness never passes ``output.google_drive_folder_id``: that would activate
Core's separate service-account publisher.
"""
from __future__ import annotations

import json
import os
import platform
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

from ..errors import HarnessError

CORE_EXECUTABLE = "litman-core"
PROVIDERS = frozenset({"codex", "claude-code"})
JOB_TYPES = frozenset({"assessment", "detailed-analysis"})
CONTRACT = 1

CORE_ERROR_MESSAGES: dict[str, str] = {
    "invalid_config": "La configuración enviada a LitMan Core es inválida",
    "invalid_input": "El expediente de entrada no es válido para el análisis",
    "llm_unavailable": "El proveedor de análisis configurado no está disponible",
    "analysis_failed": "El análisis no se pudo completar",
    "publication_failed": "No se pudo publicar el resultado del análisis",
    "internal": "LitMan Core encontró un error interno no clasificado",
}

Runner = Callable[..., subprocess.CompletedProcess]


def core_command() -> str:
    """Return the Core script installed alongside the harness interpreter."""
    name = f"{CORE_EXECUTABLE}.exe" if platform.system() == "Windows" else CORE_EXECUTABLE
    return str(Path(sys.executable).resolve().parent / name)


def core_executable() -> str | None:
    """The resolved executable if it exists and is executable (for ``diagnose``)."""
    command = core_command()
    path = Path(command)
    if not path.is_file():
        return None
    return command if platform.system() == "Windows" or path.stat().st_mode & 0o111 else None


def _required_core_command() -> str:
    command = core_executable()
    if command is None:
        raise HarnessError("core_not_installed", "LitMan Core no está instalado en el entorno del harness")
    return command


def validate_provider(provider: str) -> None:
    if provider not in PROVIDERS:
        raise HarnessError("invalid_provider", "Proveedor Core no autorizado")


def core_config(*, job_type: str, input_dir: Path, output_dir: Path, provider: str, model: str | None = None) -> str:
    """Render the exact local job; JSON escaping is valid TOML basic-string escaping.

    Only the minimal public template: no ``job.id`` (Core derives it from the
    input folder name), no ``input.kind`` (defaults to ``local``) and no
    ``[publication]`` (defaults to ``include_run_files = false``). Core
    validates its own run and leaves in ``local_path`` only the public
    artifacts, flat.  The harness relies solely on that public CLI contract
    and never reads Core's internal files.
    """
    validate_provider(provider)
    values = [json.dumps(value) for value in (job_type, str(input_dir), str(output_dir), provider)]
    text = (
        "[job]\ntype = {}\n"
        "[input]\nlocation = {}\n"
        "[output]\ndirectory = {}\n"
        "[llm]\nprovider = {}\n"
    ).format(*values)
    if model is not None:
        text += "model = {}\n".format(json.dumps(model))
    return text


def run_core(config_path: Path, run: Runner = subprocess.run) -> dict[str, Any]:
    """Run Core on a local config and return its validated success payload."""
    command = _required_core_command() if run is subprocess.run else core_command()
    result = run([command, "run", "--config", str(config_path)], text=True, encoding="utf-8",
                 errors="replace", capture_output=True, check=False, env=_child_env())
    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        raise HarnessError("core_crashed", "LitMan Core no devolvió un resultado interpretable",
                           details={"stderr": (result.stderr or "")[-1000:]})
    if not isinstance(payload, dict):
        raise HarnessError("core_crashed", "LitMan Core no devolvió un resultado interpretable",
                           details={"stderr": (result.stderr or "")[-1000:]})
    if payload.get("contract") != CONTRACT:
        raise HarnessError("core_incompatible", "LitMan Core usa una versión de contrato distinta a la esperada",
                           details={"contract": payload.get("contract")})
    if payload.get("status") == "failed":
        error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        code = error.get("code") if isinstance(error.get("code"), str) else "internal"
        message = CORE_ERROR_MESSAGES.get(code, CORE_ERROR_MESSAGES["internal"])
        raise HarnessError("core_failed", message,
                           details={"code": code, "message": error.get("message"), "local_path": payload.get("local_path")})
    if (result.returncode != 0 or payload.get("status") != "succeeded"
            or not payload.get("publication_id") or not isinstance(payload.get("local_path"), str)
            or not isinstance(payload.get("artifacts"), list)):
        raise HarnessError("invalid_core_result", "Core no devolvió una publicación validada")
    return payload


def core_info(run: Runner = subprocess.run) -> dict[str, Any] | None:
    """``litman-core info`` payload (``{"contract", "version", "providers"}``); ``None`` if it cannot be read."""
    try:
        command = _required_core_command() if run is subprocess.run else core_command()
        result = run([command, "info"], text=True, encoding="utf-8", errors="replace", capture_output=True,
                     check=False, env=_child_env())
    except Exception:  # noqa: BLE001 - informative only
        return None
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _child_env() -> dict[str, str]:
    """Ensure a Python Core child speaks UTF-8 without discarding its environment."""
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env
