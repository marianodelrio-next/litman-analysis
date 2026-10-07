import json
import stat
from pathlib import Path

import pytest

from litman_analysis.application.ports.llm import output_paths_for_run
from litman_analysis.infrastructure.llm.codex_cli import CodexProvider, CodexTimeoutError, CodexToolExecutionError


FAKE_CODEX = r'''#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path

if "sleep" in sys.argv:
    time.sleep(2)

args = sys.argv[1:]
Path("codex-argv.json").write_text(json.dumps(args), encoding="utf-8")
response_path = Path(args[args.index("--output-last-message") + 1])
sys.stdin.read()
print(json.dumps({"type": "thread.started", "thread_id": "thread-test"}), flush=True)
print(json.dumps({"type": "item.completed", "item": {"type": "command_execution", "status": "completed", "exit_code": 0}}), flush=True)
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}}), flush=True)
print("diagnóstico", file=sys.stderr, flush=True)
response_path.write_text(json.dumps({"ok": True}), encoding="utf-8")
'''


def _fake_codex(tmp_path: Path) -> Path:
    executable = tmp_path / "fake-codex"
    executable.write_text(FAKE_CODEX, encoding="utf-8")
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    return executable


def _schema(tmp_path: Path) -> Path:
    path = tmp_path / "schema.json"
    path.write_text('{"type":"object"}', encoding="utf-8")
    return path


def test_provider_separates_events_response_stderr_and_summary(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    paths = output_paths_for_run(run_dir)
    result = CodexProvider(binary=str(_fake_codex(tmp_path)), model="test-model", no_tools=False).generate(
        instructions="instructions",
        prompt="prompt",
        schema_path=_schema(tmp_path),
        case_dir=tmp_path,
        output_paths=paths,
    )

    assert result.data == {"ok": True}
    assert result.response_id == "thread-test"
    assert result.usage["total_tokens"] == 15
    assert result.execution["tool_call_count"] == 1
    args = json.loads((tmp_path / "codex-argv.json").read_text(encoding="utf-8"))
    assert 'forced_login_method="api"' in args
    assert "--dangerously-bypass-approvals-and-sandbox" in args
    assert "--sandbox" not in args
    assert "read-only" not in args
    assert "--output-schema" in args and "--output-last-message" in args
    assert len(paths.events.read_text(encoding="utf-8").splitlines()) == 3
    assert paths.stderr.read_text(encoding="utf-8").strip() == "diagnóstico"
    summary = json.loads(paths.summary.read_text(encoding="utf-8"))
    assert summary["status"] == "completed"
    assert summary["response"]["valid_json"] is True


def test_provider_enforces_timeout_and_keeps_summary(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run"
    paths = output_paths_for_run(run_dir)
    with pytest.raises(CodexTimeoutError):
        CodexProvider(
            binary=str(_fake_codex(tmp_path)), model="sleep", timeout_seconds=0.05
        ).generate(
            instructions="instructions",
            prompt="prompt",
            schema_path=_schema(tmp_path),
            case_dir=tmp_path,
            output_paths=paths,
        )

    summary = json.loads(paths.summary.read_text(encoding="utf-8"))
    assert summary["status"] == "timeout"
    assert paths.events.exists()
    assert paths.stderr.exists()


def test_provider_can_require_successful_tools_and_preserves_diagnostics(tmp_path: Path) -> None:
    executable = _fake_codex(tmp_path)
    content = executable.read_text(encoding="utf-8").replace('"exit_code": 0', '"exit_code": 23')
    executable.write_text(content, encoding="utf-8")
    paths = output_paths_for_run(tmp_path / "run")
    with pytest.raises(CodexToolExecutionError, match="herramienta requerida"):
        CodexProvider(binary=str(executable), require_successful_tools=True).generate(
            instructions="instructions", prompt="prompt", schema_path=_schema(tmp_path),
            case_dir=tmp_path, output_paths=paths,
        )
    summary = json.loads(paths.summary.read_text(encoding="utf-8"))
    assert summary["status"] == "tool_execution_error"
    assert summary["tool_calls_failed"] == 1
    assert summary["response"]["valid_json"] is True


def test_provider_accepts_search_without_matches(tmp_path: Path) -> None:
    executable = _fake_codex(tmp_path)
    content = executable.read_text(encoding="utf-8").replace(
        '"status": "completed", "exit_code": 0',
        '"command": "rg missing document.md", "status": "failed", "exit_code": 1',
    )
    executable.write_text(content, encoding="utf-8")
    paths = output_paths_for_run(tmp_path / "run")
    result = CodexProvider(binary=str(executable), require_successful_tools=True).generate(
        instructions="instructions", prompt="prompt", schema_path=_schema(tmp_path),
        case_dir=tmp_path, output_paths=paths,
    )
    assert result.data == {"ok": True}
    assert result.execution["failed_tool_call_count"] == 0
    assert result.execution["empty_search_count"] == 1
    summary = json.loads(paths.summary.read_text(encoding="utf-8"))
    assert summary["events"]["empty_searches"] == 1
