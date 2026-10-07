from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
import shlex
from typing import Any


TOOL_ITEM_TYPES = {
    "command_execution",
    "file_change",
    "mcp_tool_call",
    "web_search",
}


@dataclass
class CodexEventSummary:
    """Extrae métricas conocidas sin imponer un schema al JSONL de Codex."""

    total: int = 0
    malformed: int = 0
    by_type: Counter[str] = field(default_factory=Counter)
    item_types: Counter[str] = field(default_factory=Counter)
    tool_calls: int = 0
    failed_tool_calls: int = 0
    empty_searches: int = 0
    command_failures: list[dict[str, Any]] = field(default_factory=list)
    empty_search_details: list[dict[str, Any]] = field(default_factory=list)
    thread_id: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)

    def add(self, event: dict[str, Any]) -> None:
        self.total += 1
        event_type = str(event.get("type") or "unknown")
        self.by_type[event_type] += 1

        if event_type == "thread.started" and event.get("thread_id"):
            self.thread_id = str(event["thread_id"])

        usage = event.get("usage")
        if isinstance(usage, dict):
            self.usage = usage

        item = event.get("item")
        if not isinstance(item, dict):
            return
        item_type = str(item.get("type") or "unknown")
        self.item_types[item_type] += 1
        if event_type == "item.completed" and item_type in TOOL_ITEM_TYPES:
            self.tool_calls += 1
            if _item_failed(item):
                if item_type == "command_execution" and _is_empty_search(item):
                    self.empty_searches += 1
                    self.empty_search_details.append({
                        "program": _command_program(item.get("command")),
                        "exit_code": item.get("exit_code"),
                    })
                else:
                    self.failed_tool_calls += 1
                    if item_type == "command_execution":
                        self.command_failures.append({
                            "program": _command_program(item.get("command")),
                            "status": item.get("status"),
                            "exit_code": item.get("exit_code"),
                        })

    def add_malformed(self) -> None:
        self.total += 1
        self.malformed += 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "malformed": self.malformed,
            "by_type": dict(sorted(self.by_type.items())),
            "item_types": dict(sorted(self.item_types.items())),
            "tool_calls": self.tool_calls,
            "failed_tool_calls": self.failed_tool_calls,
            "empty_searches": self.empty_searches,
            "empty_search_details": self.empty_search_details,
            "command_failures": self.command_failures,
        }


def _item_failed(item: dict[str, Any]) -> bool:
    status = str(item.get("status") or "").lower()
    exit_code = item.get("exit_code")
    return status in {"failed", "error"} or (
        isinstance(exit_code, int) and not isinstance(exit_code, bool) and exit_code != 0
    )


def _is_empty_search(item: dict[str, Any]) -> bool:
    """Recognize only documented, non-error 'no matches' exit statuses."""
    return item.get("exit_code") == 1 and _command_program(item.get("command")) in {
        "rg", "grep", "egrep", "fgrep",
    }


def _command_program(command: object) -> str | None:
    """Extract the first program from direct commands or `sh -c` event wrappers."""
    if not isinstance(command, str) or not command.strip():
        return None
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if not tokens:
        return None
    program = Path(tokens[0]).name
    if program not in {"sh", "bash", "dash"}:
        return program
    try:
        option_index = next(index for index, token in enumerate(tokens[1:], 1)
                            if token in {"-c", "-lc", "-cl"})
        script = tokens[option_index + 1]
        lexer = shlex.shlex(script, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        inner = list(lexer)
    except (StopIteration, IndexError, ValueError):
        return None
    if any(token and set(token) <= {";", "&", "|"} for token in inner):
        return None
    return Path(inner[0]).name if inner else None
