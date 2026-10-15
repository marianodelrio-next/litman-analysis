from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from litman_core import JobRunner, __version__
from litman_core.application.job_loader import load_job
from litman_core.config import Settings
from litman_core.environment import load_env_file


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="litman-core")
    parser.add_argument("--version", action="version", version=f"litman-core {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Ejecuta config.toml")
    run.add_argument("--config", type=Path, default=Path("config.toml"))
    run.add_argument("--env-file", type=Path)
    args = parser.parse_args(argv)
    config = args.config.expanduser().resolve()
    try:
        env_file = args.env_file.expanduser().resolve() if args.env_file else config.with_name(".env")
        if args.env_file or env_file.is_file():
            load_env_file(env_file)
        job = load_job(config)
        settings = Settings()
        result = JobRunner(settings).run(job)
        payload = {"job_id": result.job_id, "publication_id": result.publication_id,
                   "status": result.status, "local_path": str(result.local_path),
                   "artifacts": [{"name": x.name, "uri": x.uri, "checksum": x.checksum} for x in result.artifacts]}
        if result.remote:
            payload["remote"] = result.remote
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    except Exception as exc:
        payload = {"status": "failed", "error": str(exc)}
        local_path = getattr(exc, "local_path", None)
        if local_path:
            payload["local_path"] = str(local_path)
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
