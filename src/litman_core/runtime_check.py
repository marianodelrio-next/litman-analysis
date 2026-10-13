"""Diagnóstico local seguro para instalaciones de LitMan Core."""
from __future__ import annotations

import shutil
import sys
import os
import stat
from pathlib import Path

from litman_core import __version__
from litman_core.config import Settings


def run_check() -> int:
    settings = Settings()
    checks = [
        ("python", sys.version_info >= (3, 11), f"{sys.version_info.major}.{sys.version_info.minor}"),
        ("package", bool(__version__), __version__),
        ("codex", shutil.which(settings.codex_binary) is not None, "installed"),
        ("node", shutil.which("node") is not None, "installed"),
        ("npm", shutil.which("npm") is not None, "installed"),
        ("chromium", any(shutil.which(name) for name in ("chromium", "google-chrome", "chromium-browser")), "installed"),
        ("rg", shutil.which("rg") is not None, "installed"),
        ("fonts", _fonts_available(), "DejaVu or Liberation Sans"),
        ("workspace", _accessible(settings.workspace_dir), str(settings.workspace_dir)),
        ("runs", _accessible(settings.runs_dir), str(settings.runs_dir)),
        ("auth-state", _auth_state(settings.codex_home_dir), "metadata only"),
    ]
    for name, ok, detail in checks:
        print(f"{name}: {'ok' if ok else 'missing'} ({detail})")
    return 0 if all(ok for _, ok, _ in checks) else 1


def _accessible(path: Path) -> bool:
    return path.is_dir() and os.access(path, os.R_OK | os.W_OK | os.X_OK)


def _fonts_available() -> bool:
    roots = (Path("/usr/share/fonts"), Path.home() / ".fonts")
    return any(root.is_dir() and any(root.rglob(pattern)) for root in roots for pattern in ("DejaVuSans.ttf", "LiberationSans-Regular.ttf"))


def _auth_state(path: Path) -> bool:
    # Solo se inspecciona tipo, legibilidad y permisos; nunca se abre el estado.
    mode = os.getenv("LITMAN_CORE_CODEX_AUTH_MODE", "chatgpt")
    if mode == "api-key":
        key = os.getenv("LITMAN_CORE_CODEX_API_KEY_FILE")
        if not key:
            return False
        candidate = Path(key).expanduser()
        try:
            info = candidate.stat()
            return stat.S_ISREG(info.st_mode) and os.access(candidate, os.R_OK) and not (stat.S_IMODE(info.st_mode) & 0o077)
        except OSError:
            return False
    if mode != "chatgpt":
        return False
    auth_file = path / "auth.json"
    try:
        info = auth_file.stat()
        return path.is_dir() and stat.S_ISREG(info.st_mode) and os.access(auth_file, os.R_OK) and not (stat.S_IMODE(info.st_mode) & 0o077)
    except OSError:
        return False
