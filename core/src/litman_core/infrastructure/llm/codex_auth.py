"""Explicit, non-interactive authentication boundary for Codex."""
from __future__ import annotations
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from litman_core.errors import CoreError

class CodexAuthenticationError(CoreError, ValueError):
    """Unsafe configuration; messages deliberately never include secret values."""

    def __init__(self, message: str) -> None:
        CoreError.__init__(self, "llm_unavailable", message)

@dataclass(frozen=True)
class CodexAuthentication:
    """One of the two supported Codex login mechanisms."""
    mode: str
    api_key_file: Path | None = None

    @classmethod
    def from_environment(cls, environ: dict[str, str] | None = None, *, codex_home: Path | None = None) -> "CodexAuthentication":
        env = os.environ if environ is None else environ
        mode = env.get("LITMAN_CORE_CODEX_AUTH_MODE", "chatgpt")
        if mode not in {"chatgpt", "api-key"}:
            raise CodexAuthenticationError("LITMAN_CORE_CODEX_AUTH_MODE debe ser chatgpt o api-key")
        api_key_file = _path(env, "LITMAN_CORE_CODEX_API_KEY_FILE")
        if mode == "api-key":
            if api_key_file is None:
                raise CodexAuthenticationError("LITMAN_CORE_CODEX_API_KEY_FILE es obligatorio para api-key")
            _validate_file(api_key_file, "LITMAN_CORE_CODEX_API_KEY_FILE")
            return cls(mode=mode, api_key_file=api_key_file)
        if api_key_file is not None:
            raise CodexAuthenticationError("la configuración de autenticación mezcla modos")
        resolved_home = codex_home or _path(env, "CODEX_HOME") or Path.home() / ".codex"
        _validate_chatgpt_state(resolved_home)
        return cls(mode=mode)

    @property
    def cli_login_method(self) -> str:
        return "api" if self.mode == "api-key" else "chatgpt"

    def environment(self) -> dict[str, str]:
        if self.mode == "api-key":
            return {"CODEX_API_KEY": _read_secret(self.api_key_file, "LITMAN_CORE_CODEX_API_KEY_FILE")}
        return {}

def _validate_chatgpt_state(codex_home: Path) -> None:
    auth_file = codex_home / "auth.json"
    _validate_file(auth_file, "CODEX_HOME/auth.json")
    if not codex_home.is_dir() or not os.access(codex_home, os.W_OK | os.X_OK):
        raise CodexAuthenticationError("CODEX_HOME debe ser un directorio escribible para renovar la sesión de ChatGPT")
    if stat.S_IMODE(auth_file.stat().st_mode) & 0o077:
        raise CodexAuthenticationError("CODEX_HOME/auth.json debe tener permisos 0600")

def _path(env: dict[str, str], name: str) -> Path | None:
    return Path(env[name]).expanduser() if env.get(name) else None

def _validate_file(path: Path, field: str) -> None:
    try:
        info = path.stat()
    except OSError as exc:
        raise CodexAuthenticationError(f"{field} debe referirse a un archivo existente y legible") from exc
    if not stat.S_ISREG(info.st_mode) or not os.access(path, os.R_OK):
        raise CodexAuthenticationError(f"{field} debe referirse a un archivo regular y legible")

def _read_secret(path: Path | None, field: str) -> str:
    if path is None:
        raise CodexAuthenticationError(f"{field} es obligatorio")
    _validate_file(path, field)
    try:
        value = path.read_text(encoding="utf-8").rstrip()
    except OSError as exc:
        raise CodexAuthenticationError(f"no se puede leer {field}") from exc
    if not value:
        raise CodexAuthenticationError(f"{field} no puede estar vacío")
    return value
