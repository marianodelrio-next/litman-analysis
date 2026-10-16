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


def output_paths_for_run(run_dir: Path, invocation_id: str | None = None) -> LLMOutputPaths:
    suffix = f"-{invocation_id}" if invocation_id else ""
    return LLMOutputPaths(
        events=run_dir / "logs" / f"llm-events{suffix}.jsonl",
        stderr=run_dir / "logs" / f"llm-stderr{suffix}.log",
        response=run_dir / "output" / f"llm-response{suffix}.json",
        summary=run_dir / "output" / f"llm-summary{suffix}.json",
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
