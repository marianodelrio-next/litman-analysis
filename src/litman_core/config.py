from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from litman_core.resource_paths import RESOURCE_ROOT


@dataclass(frozen=True)
class Settings:
    resource_root: Path = RESOURCE_ROOT
    codex_binary: str = field(default_factory=lambda: os.getenv("LITMAN_CORE_CODEX_BINARY", "codex"))
    codex_model: str | None = "gpt-5.6-luna"
    llm_provider: str = field(default_factory=lambda: os.getenv("LITMAN_CORE_LLM_PROVIDER", "codex"))
    llm_model: str | None = field(default_factory=lambda: os.getenv("LITMAN_CORE_LLM_MODEL"))
    llm_timeout_seconds: int = 1800
    claude_binary: str = field(default_factory=lambda: os.getenv("LITMAN_CORE_CLAUDE_BINARY", "claude"))
    claude_model: str | None = field(default_factory=lambda: os.getenv("LITMAN_CORE_CLAUDE_MODEL"))
    claude_config_dir: Path | None = field(default_factory=lambda: _env_path("LITMAN_CORE_CLAUDE_CONFIG_DIR"))
    codex_timeout_seconds: int = 1800
    max_file_mb: int = 25
    workspace_root: Path = field(default_factory=lambda: _env_path("LITMAN_CORE_WORKSPACE_DIR") or Path("/tmp/litman-core"))
    home_dir: Path = field(default_factory=lambda: _env_path("HOME") or Path("/tmp/litman-core/home"))
    codex_home_dir: Path = field(default_factory=lambda: _env_path("CODEX_HOME") or Path.home() / ".codex")
    google_credentials_file: Path | None = field(default_factory=lambda: _env_path("GOOGLE_APPLICATION_CREDENTIALS"))

    def __post_init__(self) -> None:
        if self.llm_provider not in {"codex", "claude-code"}:
            raise ValueError("LITMAN_CORE_LLM_PROVIDER debe ser codex o claude-code")
        for name, value in (("LITMAN_CORE_LLM_PROVIDER", self.llm_provider), ("LITMAN_CORE_LLM_MODEL", self.llm_model), ("LITMAN_CORE_CLAUDE_MODEL", self.claude_model)):
            if value is not None and not str(value).strip():
                raise ValueError(f"{name} no puede estar vacío")

    @property
    def workspace_dir(self) -> Path:
        return self.workspace_root


def _env_path(name: str) -> Path | None:
    value = os.getenv(name)
    return Path(value).expanduser() if value else None
