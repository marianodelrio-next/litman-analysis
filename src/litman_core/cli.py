from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from litman_core.application.job_loader import load_job
from litman_core.domain.jobs import JobRequest, JobType, StorageKind
from litman_core import JobRunner


def _local_job(kind: JobType, case_dir: Path, output: Path, job_id: str | None,
               options: dict[str, object] | None = None) -> JobRequest:
    location = case_dir.expanduser().resolve()
    identifier = job_id or f"{kind.value}-{hashlib.sha256(str(location).encode()).hexdigest()[:16]}"
    return JobRequest(identifier, kind, StorageKind.LOCAL, StorageKind.LOCAL, str(location), str(output.expanduser().resolve()), options or {})


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="litman-core")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Ejecuta un job JSON o YAML")
    run.add_argument("job", type=Path)
    for name in ("assess", "analyze"):
        command = commands.add_parser(name, help="Wrapper compatible")
        command.add_argument("case_dir", type=Path)
        command.add_argument("--output", type=Path, default=Path("local-data/output"))
        command.add_argument("--job-id")
        if name == "analyze":
            command.add_argument("--content-profile", choices=("skeleton-v1", "draft-v1"), default="skeleton-v1")
            command.add_argument("--output-language", choices=("auto", "es"), default="auto")
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            job = load_job(args.job)
        else:
            kind = JobType.ASSESSMENT if args.command == "assess" else JobType.DETAILED_ANALYSIS
            options = ({"generation": {"technical_document": {
                "content_profile": args.content_profile,
                "output_language": args.output_language,
            }}} if kind is JobType.DETAILED_ANALYSIS else {})
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
