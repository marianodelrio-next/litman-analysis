"""Local ``litman-core`` process boundary: explicit config.toml and execution.

The harness never passes ``output.google_drive_folder_id``: that would activate
Core's separate service-account publisher.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

from ..errors import HarnessError

CORE_EXECUTABLE = "litman-core"
PROVIDERS = frozenset({"codex", "claude-code"})
JOB_TYPES = frozenset({"assessment", "detailed-analysis"})

Runner = Callable[..., subprocess.CompletedProcess]


def core_command() -> str:
    """Return the Core script installed alongside the harness interpreter."""
    return str(Path(sys.executable).resolve().parent / CORE_EXECUTABLE)


def core_executable() -> str | None:
    """The resolved executable if it exists and is executable (for ``diagnose``)."""
    command = core_command()
    return command if Path(command).is_file() and Path(command).stat().st_mode & 0o111 else None


def _required_core_command() -> str:
    command = core_executable()
    if command is None:
        raise HarnessError("core_not_installed", "LitMan Core no está instalado en el entorno del harness")
    return command


def validate_provider(provider: str) -> None:
    if provider not in PROVIDERS:
        raise HarnessError("invalid_provider", "Proveedor Core no autorizado")


def core_config(*, job_id: str, job_type: str, input_dir: Path, output_dir: Path, provider: str) -> str:
    """Render the exact local job; JSON escaping is valid TOML basic-string escaping.

    ``include_run_files = false``: Core validates its own run and leaves in
    ``local_path`` only the public artifacts, flat.  The harness relies solely on
    that public CLI contract and never reads Core's internal files.
    """
    validate_provider(provider)
    values = [json.dumps(value) for value in (job_id, job_type, "local", str(input_dir), str(output_dir), provider)]
    return (
        "[job]\nid = {}\ntype = {}\n"
        "[input]\nkind = {}\nlocation = {}\n"
        "[output]\ndirectory = {}\n"
        "[publication]\ninclude_run_files = false\n"
        "[llm]\nprovider = {}\n"
    ).format(*values)


def run_core(config_path: Path, run: Runner = subprocess.run) -> dict[str, Any]:
    """Run Core on a local config and return its validated success payload."""
    command = _required_core_command() if run is subprocess.run else core_command()
    result = run([command, "run", "--config", str(config_path)], text=True, capture_output=True, check=False)
    if result.returncode:
        raise HarnessError("core_failed", "LitMan Core falló; el run local se conserva para diagnóstico",
                           details={"stderr": (result.stderr or "")[-1000:]})
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise HarnessError("invalid_core_result", "Core no devolvió JSON válido") from exc
    if (not isinstance(payload, dict) or payload.get("status") != "succeeded"
            or not payload.get("publication_id") or not isinstance(payload.get("local_path"), str)):
        raise HarnessError("invalid_core_result", "Core no devolvió una publicación validada")
    return payload


def core_version(run: Runner = subprocess.run) -> str | None:
    """``litman-core --version`` (e.g. ``litman-core 0.1.0``); ``None`` if it cannot be read."""
    try:
        command = _required_core_command() if run is subprocess.run else core_command()
        result = run([command, "--version"], text=True, capture_output=True, check=False)
    except Exception:  # noqa: BLE001 - the version is informative only
        return None
    parts = (result.stdout or "").split()
    return parts[-1] if result.returncode == 0 and parts else None
