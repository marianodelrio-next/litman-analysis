from litman_core.infrastructure.llm.codex_events import CodexEventSummary
import pytest


def test_event_summary_is_tolerant_and_extracts_metrics() -> None:
    summary = CodexEventSummary()
    summary.add({"type": "thread.started", "thread_id": "thread-123"})
    summary.add({
        "type": "item.completed",
        "item": {"type": "command_execution", "status": "completed", "exit_code": 0},
    })
    summary.add({
        "type": "item.completed",
        "item": {"type": "command_execution", "status": "failed", "exit_code": 2},
    })
    summary.add({"type": "future.event", "payload": {"anything": True}})
    summary.add({"type": "turn.completed", "usage": {"total_tokens": 1234}})
    summary.add_malformed()

    assert summary.thread_id == "thread-123"
    assert summary.tool_calls == 2
    assert summary.failed_tool_calls == 1
    assert summary.usage == {"total_tokens": 1234}
    assert summary.total == 6
    assert summary.malformed == 1
    assert summary.by_type["future.event"] == 1


@pytest.mark.parametrize("command", [
    "rg missing document.md",
    "/usr/bin/grep missing document.md",
    "/usr/bin/bash -lc 'rg -ni \"missing value\" documents/file.md'",
])
def test_no_match_search_is_not_a_tool_failure(command: str) -> None:
    summary = CodexEventSummary()
    summary.add({"type":"item.completed","item":{
        "type":"command_execution", "command":command,
        "status":"failed", "exit_code":1,
    }})
    assert summary.tool_calls == 1
    assert summary.empty_searches == 1
    assert summary.failed_tool_calls == 0
    assert summary.as_dict()["empty_search_details"][0]["exit_code"] == 1


@pytest.mark.parametrize("command,exit_code", [
    ("rg missing document.md", 2),
    ("/usr/bin/bash -lc 'rg missing document.md; false'", 1),
    ("sed -n 1p missing.md", 1),
    ("unknown-tool", 1),
])
def test_real_command_error_remains_fatal(command: str, exit_code: int) -> None:
    summary = CodexEventSummary()
    summary.add({"type":"item.completed","item":{
        "type":"command_execution", "command":command,
        "status":"failed", "exit_code":exit_code,
    }})
    assert summary.empty_searches == 0
    assert summary.failed_tool_calls == 1
