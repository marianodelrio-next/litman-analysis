from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from litman_core.application.job_loader import load_job
from litman_core.domain.jobs import JobRequest, JobType, StorageKind
from litman_core import JobRunner
from litman_core import __version__
from litman_core.generation_config import load_generation_config, merge_generation


def _local_job(kind: JobType, case_dir: Path, output: Path, job_id: str | None,
               options: dict[str, object] | None = None) -> JobRequest:
    location = case_dir.expanduser().resolve()
    identifier = job_id or f"{kind.value}-{hashlib.sha256(str(location).encode()).hexdigest()[:16]}"
    return JobRequest(identifier, kind, StorageKind.LOCAL, StorageKind.LOCAL, str(location), str(output.expanduser().resolve()), options or {})


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="litman-core")
    parser.add_argument("--version", action="version", version=f"litman-core {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="Comprueba requisitos locales sin leer secretos")
    run = commands.add_parser("run", help="Ejecuta un job JSON o YAML")
    run.add_argument("job", type=Path)
    run.add_argument("--config", type=Path)
    for name in ("assess", "analyze"):
        command = commands.add_parser(name, help="Wrapper compatible")
        command.add_argument("case_dir", type=Path)
        command.add_argument("--output", type=Path, default=Path("local-data/output"))
        command.add_argument("--job-id")
        command.add_argument("--config", type=Path)
        if name == "analyze":
            command.add_argument("--content-profile", choices=("skeleton-v1", "draft-v1"), default=None)
            command.add_argument("--output-language", choices=("auto", "es"), default=None)
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            from litman_core.runtime_check import run_check
            raise SystemExit(run_check())
        if args.command == "run":
            job = load_job(args.job)
            if job.job_type is JobType.DETAILED_ANALYSIS:
                configured = load_generation_config(args.config) if args.config else None
                job = JobRequest(job.job_id, job.job_type, job.input_kind, job.output_kind, job.input_location, job.output_location,
                                 {**job.options, "generation": merge_generation(configured, job.options.get("generation"))})
        else:
            kind = JobType.ASSESSMENT if args.command == "assess" else JobType.DETAILED_ANALYSIS
            options = {"generation": {"technical_document": {}}} if kind is JobType.DETAILED_ANALYSIS else {}
            if kind is JobType.DETAILED_ANALYSIS:
                if args.content_profile is not None:
                    options["generation"]["technical_document"]["content_profile"] = args.content_profile
                if args.output_language is not None:
                    options["generation"]["technical_document"]["output_language"] = args.output_language
            if args.config and kind is JobType.DETAILED_ANALYSIS:
                options["generation"] = merge_generation(load_generation_config(args.config), options["generation"])
            elif kind is JobType.DETAILED_ANALYSIS:
                options["generation"] = merge_generation(options["generation"])
            job = _local_job(kind, args.case_dir, args.output, args.job_id, options)
        result = JobRunner().run(job)
        payload = {"job_id": result.job_id, "status": result.status,
                   "run_dir": str(result.run_dir), "diagnostics_dir": str(result.diagnostics_dir),
                   "artifacts": [{"name": item.name, "uri": item.uri, "checksum": item.checksum}
                                  for item in result.artifacts]}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
