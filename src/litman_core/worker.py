"""Thin internal CLI for the unified application container."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from litman_core.application.job_loader import load_job
from litman_core.application.ports.llm import output_paths_for_run
from litman_core.config import Settings
from litman_core import JobRunner
from litman_core.infrastructure.llm.codex_auth import CodexAuthentication
from litman_core.infrastructure.llm.codex_cli import CodexProvider
from litman_core.runtime import initialize_runtime


def _jsonable(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _runtime_diagnostics() -> dict[str, object]:
    try:
        status = Path("/proc/self/status").read_text(encoding="utf-8", errors="replace")
    except OSError:
        status = ""
    selected = {line.split(":", 1)[0]: line.split(":", 1)[1].strip() for line in status.splitlines()
                if line.split(":", 1)[0] in {"CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb", "NoNewPrivs", "Seccomp"}}
    codex = subprocess.run([os.getenv("LITMAN_ANALYSIS_CODEX_BINARY", "codex"), "--version"], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return {"uid": os.getuid(), "gid": os.getgid(),
            "codex_version": codex.stdout.strip(), "codex_version_exit_code": codex.returncode,
            "process": selected}


def run_runtime_preflight(settings: Settings) -> dict[str, object]:
    """Verify the external container boundary without reading secret contents."""
    initialize_runtime(
        home=settings.home_dir,
        codex_home=settings.codex_home_dir,
        workspace=settings.workspace_dir,
        runs=settings.runs_dir,
        output=settings.local_output_dir,
        input_dir=settings.local_input_dir,
    )
    runtime = _runtime_diagnostics()
    auth = _authentication_accessible(settings)
    checks = {
        "not_root": runtime["uid"] != 0,
        "no_effective_capabilities": runtime["process"].get("CapEff") == "0000000000000000",
        "no_new_privileges": runtime["process"].get("NoNewPrivs") == "1",
        "workspace_writable": _probe_writable(settings.workspace_dir),
        "runs_writable": _probe_writable(settings.runs_dir),
        "output_writable": _probe_writable(settings.local_output_dir),
        "input_readable": settings.local_input_dir.is_dir() and os.access(settings.local_input_dir, os.R_OK | os.X_OK),
        "input_not_writable": not _probe_writable(settings.local_input_dir),
        "codex_home_writable": _probe_writable(settings.codex_home_dir),
        "codex_auth_accessible": auth,
        "google_credentials_visible": bool(settings.google_credentials_file and settings.google_credentials_file.is_file()),
        "codex_available": runtime["codex_version_exit_code"] == 0,
    }
    failures = [name for name, value in checks.items() if value is not True and name != "google_credentials_visible"]
    if failures:
        raise RuntimeError("el runtime del contenedor no cumple el contrato: " + ", ".join(failures))
    return {"kind": "runtime-preflight", "status": "ok", "runtime": runtime, "checks": checks}


def run_container_preflight(settings: Settings) -> dict[str, object]:
    """Exercise Codex file tools in the container without reading secret contents."""
    fixture = settings.local_input_dir / "fixture.md"
    if not fixture.is_file():
        raise RuntimeError("falta /input/fixture.md para el preflight integral")
    runtime = run_runtime_preflight(settings)
    diagnostics = settings.runs_dir / "_preflight" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    diagnostics.mkdir(parents=True, exist_ok=False)
    schema = diagnostics / "schema.json"
    schema.write_text('{"type":"object","additionalProperties":false,"required":["document_read","input_writable","network_available"],"properties":{"document_read":{"type":"boolean"},"input_writable":{"type":"boolean"},"network_available":{"type":"boolean"}}}', encoding="utf-8")
    auth = CodexAuthentication.from_environment(codex_home=settings.codex_home_dir)
    container_checks = {
        "workspace_writable": _probe_writable(settings.workspace_dir),
        "runs_writable": _probe_writable(diagnostics),
        "codex_auth_accessible": True,
        "google_credentials_visible": bool(
            settings.google_credentials_file and settings.google_credentials_file.is_file()),
    }
    provider = CodexProvider(binary=settings.codex_binary, model=settings.codex_model,
        timeout_seconds=settings.codex_preflight_timeout_seconds, authentication=auth,
        home=settings.home_dir, codex_home=settings.codex_home_dir, no_tools=False)
    prompt = (f"Lee únicamente {fixture}. Usa test/stat para comprobar si /input es escribible. "
              "Puedes registrar si hay conectividad de red sin descargar contenido. "
              "No busques, abras ni menciones credenciales o archivos de autenticación. Devuelve solo booleanos.")
    result = provider.generate(instructions="Preflight del contenedor unificado.", prompt=prompt, schema_path=schema,
                               case_dir=settings.local_input_dir, output_paths=output_paths_for_run(diagnostics))
    codex_checks = {key: result.data.get(key) for key in
                      ("document_read", "input_writable", "network_available")}
    expected = {"document_read": True, "input_writable": False}
    mismatches = {key: {"expected": value, "actual": codex_checks.get(key)}
                  for key, value in expected.items() if codex_checks.get(key) != value}
    if mismatches:
        raise RuntimeError(
            "el preflight integral no demostró el contrato requerido: "
            + json.dumps(mismatches, ensure_ascii=False, sort_keys=True))
    return {"kind": "container-preflight", "status": "ok", "execution": result.execution,
            "runtime": runtime, "container": container_checks, "codex": codex_checks,
            "diagnostics_dir": str(diagnostics)}


def _authentication_accessible(settings: Settings) -> bool:
    mode = os.getenv("LITMAN_ANALYSIS_CODEX_AUTH_MODE", "chatgpt")
    if mode == "chatgpt":
        auth = settings.codex_home_dir / "auth.json"
        try:
            return auth.is_file() and os.access(auth, os.R_OK) and (auth.stat().st_mode & 0o777) == 0o600
        except OSError:
            return False
    if mode == "api-key":
        value = os.getenv("LITMAN_ANALYSIS_CODEX_API_KEY_FILE")
        return bool(value and Path(value).is_file() and os.access(value, os.R_OK))
    return False


def _probe_writable(directory: Path) -> bool:
    """Exercise a writable mount using an empty private file and remove it."""
    try:
        descriptor, name = tempfile.mkstemp(prefix=".preflight-write-", dir=directory)
        os.close(descriptor)
        Path(name).unlink()
        return True
    except OSError:
        return False


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="litman-core-worker")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Ejecuta materialización, análisis y publicación")
    run.add_argument("job", type=Path)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("kind", choices=("runtime", "container"), default="runtime", nargs="?")
    args = parser.parse_args(argv)
    settings = Settings()
    try:
        if args.command == "run":
            value = _jsonable(asdict(JobRunner(settings, preflight=run_runtime_preflight).run(load_job(args.job))))
        else:
            value = run_container_preflight(settings) if args.kind == "container" else run_runtime_preflight(settings)
        print(json.dumps(value, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
