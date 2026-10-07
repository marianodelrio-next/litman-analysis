from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from litman_analysis.resource_paths import RESOURCE_ROOT


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    project_root: Path = PROJECT_ROOT
    resource_root: Path = RESOURCE_ROOT
    codex_binary: str = field(default_factory=lambda: os.getenv("LITMAN_ANALYSIS_CODEX_BINARY", "codex"))
    codex_model: str | None = field(default_factory=lambda: os.getenv("LITMAN_ANALYSIS_CODEX_MODEL") or "gpt-5.5")
    codex_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("LITMAN_ANALYSIS_CODEX_TIMEOUT_SECONDS", "1800")))
    max_file_mb: int = field(default_factory=lambda: int(os.getenv("LITMAN_ANALYSIS_MAX_FILE_MB", "25")))
    codex_context_window_tokens: int = field(default_factory=lambda: int(os.getenv("LITMAN_ANALYSIS_CODEX_CONTEXT_WINDOW_TOKENS", "1050000")))
    codex_context_reserve_tokens: int = field(default_factory=lambda: int(os.getenv("LITMAN_ANALYSIS_CODEX_CONTEXT_RESERVE_TOKENS", "50000")))
    codex_preflight: bool = field(default_factory=lambda: _env_bool("LITMAN_ANALYSIS_CODEX_PREFLIGHT", True))
    codex_preflight_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("LITMAN_ANALYSIS_CODEX_PREFLIGHT_TIMEOUT_SECONDS", "120")))
    runs_root: Path | None = field(default_factory=lambda: _env_path("LITMAN_ANALYSIS_RUNS_DIR"))
    workspace_root: Path = field(default_factory=lambda: _env_path("LITMAN_ANALYSIS_WORKSPACE_DIR") or Path("/tmp/litman-analysis"))
    home_dir: Path = field(default_factory=lambda: _env_path("HOME") or Path("/tmp/litman-analysis/home"))
    codex_home_dir: Path = field(default_factory=lambda: _env_path("CODEX_HOME") or Path.home() / ".codex")
    google_credentials_file: Path | None = field(default_factory=lambda: _env_path("GOOGLE_APPLICATION_CREDENTIALS"))
    local_input_dir: Path = field(default_factory=lambda: _env_path("LITMAN_ANALYSIS_INPUT_DIR") or Path("/input"))
    local_output_dir: Path = field(default_factory=lambda: _env_path("LITMAN_ANALYSIS_OUTPUT_DIR") or Path("/output"))

    @property
    def runs_dir(self) -> Path:
        return self.runs_root or self.project_root / "runs"

    @property
    def workspace_dir(self) -> Path:
        return self.workspace_root


def _env_path(name: str) -> Path | None:
    value = os.getenv(name)
    return Path(value).expanduser() if value else None


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    if value.lower() in {"1", "true", "yes"}:
        return True
    if value.lower() in {"0", "false", "no"}:
        return False
    raise ValueError(f"{name} debe ser true o false")
