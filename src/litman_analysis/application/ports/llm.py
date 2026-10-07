from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class LLMOutputPaths:
    events: Path
    stderr: Path
    response: Path
    summary: Path


def output_paths_for_run(run_dir: Path) -> LLMOutputPaths:
    return LLMOutputPaths(
        events=run_dir / "logs" / "codex-events.jsonl",
        stderr=run_dir / "logs" / "codex-stderr.log",
        response=run_dir / "output" / "codex-response.json",
        summary=run_dir / "output" / "codex-summary.json",
    )


@dataclass(frozen=True)
class LLMResult:
    data: dict
    provider: str
    model: str
    response_id: str | None
    usage: dict
    execution: dict


class LLMProvider(Protocol):
    def generate(self, *, instructions: str, prompt: str, schema_path: Path,
                 case_dir: Path, output_paths: LLMOutputPaths) -> LLMResult:
        ...
