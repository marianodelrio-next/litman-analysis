"""Check for a newer tagged LitMan release without changing the installation."""
from __future__ import annotations

import json
import os
import platform as host_platform
import re
import shutil
import subprocess
from typing import Callable, Mapping

from . import __version__
from .errors import HarnessError
from .installation import manifest_path

Runner = Callable[..., subprocess.CompletedProcess]
_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
_SECTION = re.compile(r"^## \[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2})\s*$", re.M)


def _version(value: str) -> tuple[int, int, int]:
    match = _TAG.fullmatch("v" + value)
    if match is None:
        raise ValueError("invalid version")
    return tuple(map(int, match.groups()))


def _changes(changelog: str, installed: str, latest: str) -> list[dict[str, str]]:
    sections = list(_SECTION.finditer(changelog))
    result = []
    for index, section in enumerate(sections):
        version = section.group(1)
        if _version(installed) < _version(version) <= _version(latest):
            end = sections[index + 1].start() if index + 1 < len(sections) else len(changelog)
            result.append({"version": version, "date": section.group(2),
                           "text": changelog[section.end():end].strip()})
    result.reverse()
    return result


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def check_update(*, env: Mapping[str, str] | None = None, run: Runner = subprocess.run,
                 which: Callable[[str], str | None] = shutil.which,
                 system: str | None = None) -> dict[str, object]:
    env = os.environ if env is None else env
    source = None
    try:
        manifest = manifest_path(env)
        data = json.loads(manifest.read_text(encoding="utf-8"))
        source = data.get("source")
    except (OSError, ValueError, TypeError):
        pass
    if not source:
        raise HarnessError("update_source_missing", "No se encuentra el origen de esta instalación")
    git = which("git")
    if not git:
        raise HarnessError("update_check_failed", "No se pudo comprobar si hay una versión nueva")
    try:
        fetched = run([git, "-C", source, "fetch", "--tags", "--quiet"], capture_output=True,
                      text=True, encoding="utf-8", check=False)
        if fetched.returncode != 0:
            raise OSError("git fetch failed")
        listed = run([git, "-C", source, "tag", "-l", "v*"], capture_output=True, text=True,
                     encoding="utf-8", check=False)
        if listed.returncode != 0:
            raise OSError("git tag failed")
        tags = [match for tag in listed.stdout.splitlines() if (match := _TAG.fullmatch(tag))]
        latest_match = max(tags, key=lambda match: tuple(map(int, match.groups()))) if tags else None
        latest = ".".join(latest_match.groups()) if latest_match else None
        available = latest is not None and _version(latest) > _version(__version__)
        changes: list[dict[str, str]] = []
        if available:
            shown = run([git, "-C", source, "show", f"v{latest}:CHANGELOG.md"], capture_output=True,
                        text=True, encoding="utf-8", check=False)
            if shown.returncode != 0:
                raise OSError("release changelog unavailable")
            changes = _changes(shown.stdout, __version__, latest)
        app = data.get("app")
        command = None
        if available:
            system = system or host_platform.system()
            if system == "Windows":
                app_arg = _powershell_quote(str(app))
                source_arg = _powershell_quote(str(source))
                script_arg = _powershell_quote(str(source) + r"\harness\deployment\install.ps1")
                command = (f"$env:LITMAN_APP={app_arg}; $env:LITMAN_SRC_DIR={source_arg}; powershell "
                           f"-NoProfile -ExecutionPolicy Bypass -File {script_arg}")
            elif system in {"Linux", "Darwin"}:
                import shlex
                command = (f"LITMAN_APP={shlex.quote(str(app))} LITMAN_SRC_DIR={shlex.quote(str(source))} sh "
                           f"{shlex.quote(str(source) + '/harness/deployment/install.sh')}")
            else:
                raise OSError("unsupported platform")
        return {"installed": __version__, "latest": latest, "update_available": bool(available),
                "changes": changes, "command": command}
    except (OSError, UnicodeError, AttributeError, ValueError) as exc:
        raise HarnessError("update_check_failed", "No se pudo comprobar si hay una versión nueva") from exc
