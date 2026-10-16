"""Single provider table shared by Codex and Claude Code resolution."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderSpec:
    binary_env: str
    default_binary: str
    model: str


PROVIDERS: dict[str, ProviderSpec] = {
    "codex": ProviderSpec(
        binary_env="LITMAN_CORE_CODEX_BINARY",
        default_binary="codex",
        model="gpt-5.6-luna",
    ),
    "claude-code": ProviderSpec(
        binary_env="LITMAN_CORE_CLAUDE_BINARY",
        default_binary="claude",
        model="claude-sonnet-5",
    ),
}
