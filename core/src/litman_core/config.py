from __future__ import annotations

import os
import platform
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from litman_core.resource_paths import RESOURCE_ROOT


@dataclass(frozen=True)
class Settings:
    resource_root: Path = RESOURCE_ROOT
    codex_binary: str = field(default_factory=lambda: os.getenv("LITMAN_CORE_CODEX_BINARY", "codex"))
    # llm_provider/llm_model are not read from the environment: the TOML is
    # the only source. JobRunner resolves the job's selection via
    # ``resolve_llm`` and copies it here with ``replace()`` before building
    # the provider, so pipelines reading ``settings.llm_provider``/
    # ``llm_model`` always see the already-resolved selection for this run.
    llm_provider: str = "codex"
    llm_model: str | None = None
    llm_timeout_seconds: int = 1800
    claude_binary: str = field(default_factory=lambda: os.getenv("LITMAN_CORE_CLAUDE_BINARY", "claude"))
    claude_config_dir: Path | None = field(default_factory=lambda: _env_path("LITMAN_CORE_CLAUDE_CONFIG_DIR"))
    max_file_mb: int = 25
    workspace_root: Path = field(default_factory=lambda: _env_path("LITMAN_CORE_WORKSPACE_DIR") or _default_workspace())
    home_dir: Path = field(default_factory=lambda: _env_path("HOME") or _default_home())
    codex_home_dir: Path = field(default_factory=lambda: _env_path("CODEX_HOME") or Path.home() / ".codex")
    google_credentials_file: Path | None = field(default_factory=lambda: _env_path("GOOGLE_APPLICATION_CREDENTIALS"))

    @property
    def workspace_dir(self) -> Path:
        return self.workspace_root


def _env_path(name: str) -> Path | None:
    value = os.getenv(name)
    return Path(value).expanduser() if value else None


def _default_workspace() -> Path:
    if platform.system() == "Windows":
        return Path(tempfile.gettempdir()) / "litman-core"
    return Path("/tmp/litman-core")


def _default_home() -> Path:
    if platform.system() == "Windows":
        return Path.home()
    return Path("/tmp/litman-core/home")
