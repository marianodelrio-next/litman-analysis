from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
from pathlib import Path

from litman_core import JobRunner, __version__
from litman_core.application.job_loader import load_job
from litman_core.config import Settings
from litman_core.environment import load_env_file
from litman_core.errors import CoreError
from litman_core.infrastructure.llm.providers import PROVIDERS

CONTRACT = 1


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="litman-core")
    parser.add_argument("--version", action="version", version=f"litman-core {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Ejecuta config.toml")
    run.add_argument("--config", type=Path, default=Path("config.toml"))
    run.add_argument("--env-file", type=Path)
    commands.add_parser("info", help="Versión y contrato de litman-core")
    args = parser.parse_args(argv)
    if args.command == "info":
        _info()
        return
    _run(args)


def _info() -> None:
    payload = {"contract": CONTRACT, "version": __version__, "providers": sorted(PROVIDERS),
               "environment": _environment()}
    _emit_json(payload)


def _environment() -> dict[str, object]:
    """Local-only checks (never executes a provider CLI or a browser)."""
    from litman_core.generation.opportunity_report.generator import _find_browser

    providers: dict[str, dict[str, bool]] = {}
    for name, spec in PROVIDERS.items():
        binary = os.environ.get(spec.binary_env) or spec.default_binary
        cli_found = shutil.which(binary) is not None
        if name == "codex":
            codex_home = os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")
            session = (Path(codex_home) / "auth.json").is_file()
        else:
            config_dir = (os.environ.get("LITMAN_CORE_CLAUDE_CONFIG_DIR")
                          or os.environ.get("CLAUDE_CONFIG_DIR")
                          or str(Path.home() / ".claude"))
            session = (Path(config_dir) / ".credentials.json").is_file() or bool(os.environ.get("ANTHROPIC_API_KEY"))
        providers[name] = {"cli": cli_found, "session": session}
    pdf_browser = _find_browser("google-chrome") is not None
    return {"providers": providers, "pdf_browser": pdf_browser}


def _run(args: argparse.Namespace) -> None:
    config = args.config.expanduser().resolve()
    try:
        try:
            env_file = args.env_file.expanduser().resolve() if args.env_file else config.with_name(".env")
            if args.env_file or env_file.is_file():
                load_env_file(env_file)
            job = load_job(config)
            settings = Settings()
        except Exception as exc:
            raise CoreError("invalid_config", str(exc)) from exc
        result = JobRunner(settings).run(job)
        payload = {
            "contract": CONTRACT,
            "status": "succeeded",
            "job_id": result.job_id,
            "publication_id": result.publication_id,
            "local_path": str(result.local_path),
            "artifacts": [
                {"role": x.role, "name": x.name, "uri": x.uri, "checksum": x.checksum}
                for x in result.artifacts
            ],
        }
        if result.remote:
            payload["remote"] = result.remote
        _emit_json(payload)
    except Exception as exc:
        code = exc.code if isinstance(exc, CoreError) else "internal"
        message = exc.message if isinstance(exc, CoreError) else str(exc)
        payload: dict[str, object] = {"contract": CONTRACT, "status": "failed", "error": {"code": code, "message": message}}
        local_path = getattr(exc, "local_path", None)
        if local_path:
            payload["local_path"] = str(local_path)
        _emit_json(payload)
        raise SystemExit(1) from exc


def _emit_json(payload: dict[str, object]) -> None:
    if platform.system() == "Windows" and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
