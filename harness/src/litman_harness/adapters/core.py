"""Local ``litman-core`` process boundary: explicit config.toml and execution.

The harness never passes ``output.google_drive_folder_id``: that would activate
Core's separate service-account publisher.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Callable

from ..errors import HarnessError
from ..local_paths import CORE_ENV

CORE_EXECUTABLE = "litman-core"
PROVIDERS = frozenset({"codex", "claude-code"})
JOB_TYPES = frozenset({"assessment", "detailed-analysis"})

Runner = Callable[..., subprocess.CompletedProcess]


def core_command() -> str:
    """``LITMAN_HARNESS_CORE`` when configured (e.g. the root ``.venv`` in development), else ``PATH``."""
    configured = os.environ.get(CORE_ENV)
    return str(Path(configured).expanduser()) if configured else CORE_EXECUTABLE


def core_executable() -> str | None:
    """The resolved executable if it exists and is executable (for ``diagnose``)."""
    command = core_command()
    if os.environ.get(CORE_ENV):
        return command if os.path.isfile(command) and os.access(command, os.X_OK) else None
    return shutil.which(command)


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
    result = run([core_command(), "run", "--config", str(config_path)], text=True, capture_output=True, check=False)
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
        result = run([core_command(), "--version"], text=True, capture_output=True, check=False)
    except Exception:  # noqa: BLE001 - the version is informative only
        return None
    parts = (result.stdout or "").split()
    return parts[-1] if result.returncode == 0 and parts else None
