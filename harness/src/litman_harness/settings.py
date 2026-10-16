"""Local, per-machine setup: provider (and optional model) chosen once via `setup`.

Never Drive, never a plan: this is the operation's own local mutation. The
settings file lives under the harness config directory, outside the
checkout, with restrictive permissions (0700 directory, 0600 file).
"""
from __future__ import annotations

import json
import os
import subprocess
import tomllib
from typing import Any, Mapping

from .adapters import core
from .errors import HarnessError
from .local_paths import config_dir, settings_path


def load_settings(env: Mapping[str, str]) -> dict[str, Any] | None:
    """Return the locally saved ``{"provider", "model"?}``, or ``None`` if unset."""
    path = settings_path(env)
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise HarnessError("invalid_settings", "El archivo local de ajustes no es TOML válido") from exc
    provider = data.get("provider")
    model = data.get("model")
    if not isinstance(provider, str) or not provider:
        raise HarnessError("invalid_settings", "El ajuste local 'provider' es obligatorio y debe ser texto")
    if model is not None and (not isinstance(model, str) or not model):
        raise HarnessError("invalid_settings", "El ajuste local 'model' debe ser texto no vacío")
    result: dict[str, Any] = {"provider": provider}
    if model is not None:
        result["model"] = model
    return result


def setup(env: Mapping[str, str], provider: str, model: str | None = None, *,
          run: core.Runner = subprocess.run) -> dict[str, Any]:
    """Validate the provider against the installed Core and persist the local choice."""
    if core.core_executable() is None:
        raise HarnessError("core_not_installed", "LitMan Core no está instalado en el entorno del harness")
    info = core.core_info(run)
    if info is None:
        raise HarnessError("core_crashed", "No se pudo leer la información de LitMan Core")
    if info.get("contract") != core.CONTRACT:
        raise HarnessError("core_incompatible", "LitMan Core usa una versión de contrato distinta a la esperada",
                           details={"contract": info.get("contract")})
    providers = info.get("providers")
    if not isinstance(providers, list) or provider not in providers:
        raise HarnessError("invalid_provider", "Proveedor no admitido por la instalación de LitMan Core",
                           details={"providers": providers})
    directory = config_dir(env)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    text = f"provider = {json.dumps(provider)}\n"
    if model is not None:
        text += f"model = {json.dumps(model)}\n"
    path = settings_path(env)
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)
    result = {"provider": provider, "contract": info.get("contract"), "core_version": info.get("version")}
    if model is not None:
        result["model"] = model
    return result
