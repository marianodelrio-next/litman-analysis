"""Idempotent local install/uninstall of LitMan skills, subagent and MCP registration.

Reads skills, the workspace template and the subagent only from the cloned
repository given as ``source``; writes only inside ``home`` (workspace,
skills, subagent) and inside the harness config/state directories
(``local_paths``). Every path written is recorded in a manifest so
``uninstall`` only removes what ``install`` put there. Never touches Drive,
never executes Git, uv, a provider CLI or a browser.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import stat
import subprocess
import tomllib
from pathlib import Path
from typing import Any, Callable, Mapping

from .adapters.core import Runner, script_path
from .adapters.oauth import write_private
from .errors import HarnessError
from .local_paths import client_path, config_dir, plan_store_root, settings_path, state_dir, token_path, work_root

APPS = ("codex", "claude")
SKILL_NAMES = ("conectar-licitacion", "resumir-licitacion", "preparar-equipo", "ayuda-litman")
SUBAGENT_NAME = "lector-licitacion"
CODEX_BLOCK_START = "# >>> litman (gestionado por `litman install`; no editar) >>>"
CODEX_BLOCK_END = "# <<< litman <<<"
MAX_OAUTH_CLIENT_BYTES = 64 * 1024
CLAUDE_TIMEOUT_MS = "7200000"


def manifest_path(env: Mapping[str, str]) -> Path:
    return state_dir(env) / "install-manifest.json"


def _read_manifest(env: Mapping[str, str]) -> dict[str, Any]:
    path = manifest_path(env)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_manifest(env: Mapping[str, str], data: dict[str, Any]) -> None:
    write_private(manifest_path(env), json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2))


def _remove(path: Path, *, is_dir: bool) -> bool:
    """Remove a file or tree, retrying Windows read-only targets; return False instead of raising."""
    try:
        if is_dir:
            if platform.system() == "Windows":
                shutil.rmtree(path, onerror=_remove_readonly)
            else:
                shutil.rmtree(path)
        else:
            try:
                path.unlink()
            except OSError:
                if platform.system() != "Windows":
                    raise
                os.chmod(path, stat.S_IWRITE)
                path.unlink()
    except OSError:
        return False
    return True


def _remove_readonly(function: Callable[..., Any], path: str, _exc_info: Any) -> None:
    """Retry only Windows read-only files; other deletion failures still surface."""
    os.chmod(path, stat.S_IWRITE)
    function(path)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def render_codex_block(command: str) -> str:
    return (f"{CODEX_BLOCK_START}\n"
            "[mcp_servers.litman]\n"
            f"command = {json.dumps(command)}\n"
            "args = []\n"
            "tool_timeout_sec = 7200\n"
            f"{CODEX_BLOCK_END}\n")


def strip_codex_block(text: str) -> str:
    """Remove the delimited litman block, leaving everything else byte for byte."""
    if CODEX_BLOCK_START not in text or CODEX_BLOCK_END not in text:
        return text
    before, _, rest = text.partition(CODEX_BLOCK_START)
    _, _, after = rest.partition(CODEX_BLOCK_END)
    after = after[1:] if after.startswith("\n") else after
    before = before.rstrip("\n")
    if before and after.strip("\n"):
        return before + "\n\n" + after
    return before + after


def _codex_home(home: Path, env: Mapping[str, str]) -> Path:
    value = env.get("CODEX_HOME")
    return Path(value).expanduser() if value else home / ".codex"


def _app_paths(app: str, home: Path, env: Mapping[str, str]) -> dict[str, Path]:
    if app == "codex":
        codex_home = _codex_home(home, env)
        return {"skills": home / ".agents" / "skills", "agents": codex_home / "agents",
                "config": codex_home / "config.toml"}
    return {"skills": home / ".claude" / "skills", "agents": home / ".claude" / "agents",
            "settings": home / ".claude" / "settings.json"}


def _subagent_source(source: Path, app: str) -> Path:
    ext = "toml" if app == "codex" else "md"
    return source / "harness" / "agent" / app / "agents" / f"{SUBAGENT_NAME}.{ext}"


def _subagent_dest(paths: dict[str, Path], app: str) -> Path:
    ext = "toml" if app == "codex" else "md"
    return paths["agents"] / f"{SUBAGENT_NAME}.{ext}"


def litman_command() -> str:
    """Return the ``litman`` command the product agent is told to run.

    On Windows it runs the CLI module through the tool environment's
    ``python.exe`` (with the PowerShell call operator): Smart App Control may
    block the uv-generated ``litman.exe`` launcher.
    """
    if platform.system() == "Windows":
        return f'& "{script_path("python")}" -m litman_harness.interfaces.cli'
    return str(script_path("litman"))


def install(*, app: str, source: Path, home: Path, env: Mapping[str, str],
            run: Runner = subprocess.run) -> dict[str, Any]:
    """Create or update the workspace, skills, subagent and MCP registration for ``app``."""
    if app not in APPS:
        raise HarnessError("invalid_source", "Aplicación no admitida", details={"app": app})
    source = Path(source)
    skills_src = source / "harness" / "agent" / "skills"
    workspace_src = source / "harness" / "agent" / "workspace" / "AGENTS.md"
    if not skills_src.is_dir() or not workspace_src.is_file():
        raise HarnessError("invalid_source", "La ruta de origen no contiene harness/agent")
    for name in SKILL_NAMES:
        if not (skills_src / name).is_dir():
            raise HarnessError("invalid_source", "Falta una skill en el origen", details={"skill": name})
    subagent_src = _subagent_source(source, app)
    if not subagent_src.is_file():
        raise HarnessError("invalid_source", "La ruta de origen no contiene el subagente de esta app")

    paths = _app_paths(app, home, env)
    manifest = _read_manifest(env)
    warnings: list[str] = []

    # --- conflict detection: nothing is written until every check passes ---
    known_skills = set(manifest.get("skills") or []) if manifest.get("app") == app else set()
    for name in SKILL_NAMES:
        dest = paths["skills"] / name
        if dest.exists() and name not in known_skills:
            raise HarnessError("install_conflict", "Ya existe una carpeta de skill con ese nombre",
                                details={"path": name})
    subagent_dest = _subagent_dest(paths, app)
    known_subagent = manifest.get("subagent") if manifest.get("app") == app else None
    if subagent_dest.exists() and known_subagent != SUBAGENT_NAME:
        raise HarnessError("install_conflict", "Ya existe un subagente con ese nombre",
                            details={"path": subagent_dest.name})

    litman_bin = litman_command()
    litman_mcp = str(script_path("litman-mcp"))

    codex_new_config_text: str | None = None
    claude_bin: str | None = None
    claude_registered_by_us = False
    claude_settings_data: dict[str, Any] = {}
    claude_timeout_to_write = False
    if app == "codex":
        config_path = paths["config"]
        existing = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
        stripped = strip_codex_block(existing)
        try:
            parsed = tomllib.loads(stripped)
        except tomllib.TOMLDecodeError as exc:
            raise HarnessError("invalid_codex_config", "config.toml existente no es TOML válido") from exc
        if isinstance(parsed.get("mcp_servers"), dict) and "litman" in parsed["mcp_servers"]:
            raise HarnessError("install_conflict", "Ya existe un servidor MCP litman ajeno en config.toml")
        block = render_codex_block(litman_mcp)
        new_text = stripped.rstrip("\n")
        new_text = f"{new_text}\n\n{block}" if new_text else block
        tomllib.loads(new_text)  # re-validate the whole file before writing anything
        codex_new_config_text = new_text
    else:
        claude_bin = shutil.which("claude")
        if claude_bin is None:
            raise HarnessError("claude_cli_missing", "No se encuentra la CLI `claude` en el PATH")
        registered_elsewhere = bool(manifest.get("mcp_registered") and manifest.get("app") == "claude")
        get_result = run([claude_bin, "mcp", "get", "litman"], capture_output=True, text=True, check=False)
        if get_result.returncode == 0:
            if not registered_elsewhere:
                raise HarnessError("install_conflict", "Ya existe un servidor MCP litman ajeno en Claude Code")
            claude_registered_by_us = True
        settings_path_ = paths["settings"]
        if settings_path_.is_file():
            try:
                claude_settings_data = json.loads(settings_path_.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise HarnessError("invalid_claude_settings", "settings.json de Claude no es JSON válido") from exc
            if not isinstance(claude_settings_data, dict):
                raise HarnessError("invalid_claude_settings", "settings.json de Claude no es un objeto JSON")
        existing_timeout_env = claude_settings_data.get("env")
        claude_timeout_to_write = not (isinstance(existing_timeout_env, dict)
                                        and "MCP_TOOL_TIMEOUT" in existing_timeout_env)

    workspace_dir = home / "LitMan"
    workspace_dest = workspace_dir / "AGENTS.md"
    workspace_already_ours = bool(manifest.get("workspace_created"))
    workspace_created_now = not workspace_dir.exists()
    workspace_is_ours = workspace_already_ours or workspace_created_now or not workspace_dest.is_file()

    claude_md = workspace_dir / "CLAUDE.md"
    claude_md_already_ours = bool(manifest.get("claude_md_created")) if manifest.get("app") == app else False
    claude_md_is_ours = app == "claude" and (workspace_is_ours or claude_md_already_ours or not claude_md.is_file())

    # --- apply: every check above passed, now write ---
    installed: list[str] = []
    workspace_dir.mkdir(parents=True, exist_ok=True)
    if workspace_is_ours:
        template = workspace_src.read_text(encoding="utf-8").replace("{{LITMAN_BIN}}", litman_bin)
        workspace_dest.write_text(template, encoding="utf-8")
        installed.append("workspace")
    else:
        warnings.append("AGENTS.md ya existe en LitMan/ y no fue creado por `litman install`; no se modifica")
    if claude_md_is_ours:
        claude_md.write_text("@AGENTS.md\n", encoding="utf-8")
        installed.append("claude_md")

    paths["skills"].mkdir(parents=True, exist_ok=True)
    for name in SKILL_NAMES:
        dest = paths["skills"] / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(skills_src / name, dest)
    installed.append("skills")

    subagent_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(subagent_src, subagent_dest)
    installed.append("subagent")

    claude_timeout_written = False
    if app == "codex":
        _atomic_write(paths["config"], codex_new_config_text)
        installed.append("mcp")
    else:
        if claude_registered_by_us:
            run([claude_bin, "mcp", "remove", "--scope", "user", "litman"], capture_output=True, text=True,
                check=False)
        add_result = run([claude_bin, "mcp", "add", "--scope", "user", "litman", "--", litman_mcp],
                         capture_output=True, text=True, check=False)
        if add_result.returncode != 0:
            raise HarnessError("claude_mcp_failed", "No se pudo registrar el MCP en Claude Code",
                                details={"stderr": (getattr(add_result, "stderr", "") or "")[-500:]})
        installed.append("mcp")
        if claude_timeout_to_write:
            claude_settings_data.setdefault("env", {})
            claude_settings_data["env"]["MCP_TOOL_TIMEOUT"] = CLAUDE_TIMEOUT_MS
            write_private(paths["settings"], json.dumps(claude_settings_data, ensure_ascii=False, indent=2))
            installed.append("claude_timeout_env")
            claude_timeout_written = True

    new_manifest: dict[str, Any] = {
        "app": app,
        "workspace_created": workspace_already_ours or workspace_created_now,
        "skills": list(SKILL_NAMES),
        "subagent": SUBAGENT_NAME,
        "mcp_registered": True,
        "oauth_client": bool(manifest.get("oauth_client")),
    }
    if app == "claude":
        new_manifest["claude_timeout_env_set"] = claude_timeout_written or bool(manifest.get("claude_timeout_env_set"))
        new_manifest["claude_md_created"] = claude_md_is_ours
    _write_manifest(env, new_manifest)
    return {"app": app, "installed": installed, "warnings": warnings,
            "next": 'Cierra y reabre la app, abre la carpeta LitMan y escribe "prepara mi equipo".'}


def import_oauth_client(path: Path, *, delete_original: bool = False, env: Mapping[str, str]) -> dict[str, Any]:
    """Validate, copy privately and register the Drive OAuth client (``installed`` type only)."""
    source = Path(path)
    if not source.is_file():
        raise HarnessError("invalid_oauth_client", "El archivo de cliente OAuth no existe")
    if source.stat().st_size > MAX_OAUTH_CLIENT_BYTES:
        raise HarnessError("invalid_oauth_client", "El archivo de cliente OAuth es demasiado grande")
    try:
        text = source.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HarnessError("invalid_oauth_client", "El archivo de cliente OAuth no es JSON válido") from exc
    if not isinstance(data, dict) or not isinstance(data.get("installed"), dict):
        raise HarnessError("invalid_oauth_client", "El cliente OAuth debe ser de tipo 'installed'")
    installed = data["installed"]
    for field in ("client_id", "client_secret", "auth_uri", "token_uri"):
        value = installed.get(field)
        if not isinstance(value, str) or not value:
            raise HarnessError("invalid_oauth_client", "Falta un campo obligatorio del cliente OAuth")

    dest = client_path(env)
    write_private(dest, text)
    if delete_original and source.resolve() != dest.resolve():
        source.unlink()

    manifest = _read_manifest(env)
    manifest["oauth_client"] = True
    _write_manifest(env, manifest)
    return {"ok": True, "imported": True}


def uninstall(*, home: Path, env: Mapping[str, str], remove_workspace: bool = False, purge_data: bool = False,
              run: Runner = subprocess.run) -> dict[str, Any]:
    """Remove exactly what the manifest recorded, never more."""
    manifest = _read_manifest(env)
    if not manifest:
        return {"removed": [], "kept": [], "failed": []}

    removed: list[str] = []
    kept: list[str] = []
    failed: list[str] = []
    app = manifest.get("app")
    paths = _app_paths(app, home, env) if app in APPS else None

    if paths:
        for name in manifest.get("skills") or []:
            dest = paths["skills"] / name
            if dest.exists():
                (removed if _remove(dest, is_dir=True) else failed).append(f"skill:{name}")
        subagent = manifest.get("subagent")
        if subagent:
            dest = _subagent_dest(paths, app)
            if dest.exists():
                (removed if _remove(dest, is_dir=False) else failed).append("subagent")

    if manifest.get("mcp_registered") and paths:
        if app == "codex":
            config_path = paths["config"]
            if config_path.is_file():
                text = config_path.read_text(encoding="utf-8")
                stripped = strip_codex_block(text)
                if stripped != text:
                    _atomic_write(config_path, stripped)
                    removed.append("mcp")
        else:
            claude_bin = shutil.which("claude")
            if claude_bin:
                run([claude_bin, "mcp", "remove", "--scope", "user", "litman"], capture_output=True, text=True,
                    check=False)
                removed.append("mcp")
            if manifest.get("claude_timeout_env_set"):
                settings_path_ = paths["settings"]
                if settings_path_.is_file():
                    try:
                        data = json.loads(settings_path_.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        data = None
                    if (isinstance(data, dict) and isinstance(data.get("env"), dict)
                            and data["env"].get("MCP_TOOL_TIMEOUT") == CLAUDE_TIMEOUT_MS):
                        del data["env"]["MCP_TOOL_TIMEOUT"]
                        write_private(settings_path_, json.dumps(data, ensure_ascii=False, indent=2))
                        removed.append("claude_timeout_env")

    workspace_dir = home / "LitMan"
    if manifest.get("claude_md_created"):
        if remove_workspace:
            claude_md = workspace_dir / "CLAUDE.md"
            if claude_md.exists():
                (removed if _remove(claude_md, is_dir=False) else failed).append("claude_md")
        else:
            kept.append("claude_md")

    if manifest.get("workspace_created"):
        if remove_workspace:
            if workspace_dir.exists():
                (removed if _remove(workspace_dir, is_dir=True) else failed).append("workspace")
        else:
            kept.append("workspace")

    if purge_data:
        if manifest.get("oauth_client"):
            client = client_path(env)
            if client.is_file():
                (removed if _remove(client, is_dir=False) else failed).append("oauth_client")
        token = token_path(env)
        if token.is_file():
            (removed if _remove(token, is_dir=False) else failed).append("token")
        settings_file = settings_path(env)
        if settings_file.is_file():
            (removed if _remove(settings_file, is_dir=False) else failed).append("settings")
        for root in (plan_store_root(env), work_root(env)):
            if root.exists():
                (removed if _remove(root, is_dir=True) else failed).append(str(root.name))
    else:
        if manifest.get("oauth_client"):
            kept.append("oauth_client")

    if not failed:
        manifest_path(env).unlink(missing_ok=True)
    return {"removed": removed, "kept": kept, "failed": failed}


def status(*, env: Mapping[str, str], home: Path | None = None) -> dict[str, Any]:
    """Installation report for ``diagnose``; never raises, never a real path in the output."""
    try:
        manifest = _read_manifest(env)
    except Exception:  # noqa: BLE001 - diagnose must never crash
        return {"installed": False}
    if not manifest:
        return {"installed": False}
    app = manifest.get("app")
    if app not in APPS:
        return {"installed": False}
    try:
        base_home = home if home is not None else Path.home()
        paths = _app_paths(app, base_home, env)
        skills = manifest.get("skills") or []
        skills_ok = bool(skills) and all((paths["skills"] / name).exists() for name in skills)
        subagent = manifest.get("subagent")
        subagent_ok = bool(subagent) and _subagent_dest(paths, app).exists()
        workspace_ok = (base_home / "LitMan" / "AGENTS.md").is_file()
    except Exception:  # noqa: BLE001 - diagnose must never crash
        return {"installed": True, "app": app, "workspace": False, "skills": False, "subagent": False,
                 "mcp_registered": bool(manifest.get("mcp_registered")),
                 "oauth_client_imported": bool(manifest.get("oauth_client"))}
    return {
        "installed": True,
        "app": app,
        "workspace": workspace_ok,
        "skills": skills_ok,
        "subagent": subagent_ok,
        "mcp_registered": bool(manifest.get("mcp_registered")),
        "oauth_client_imported": bool(manifest.get("oauth_client")),
    }
