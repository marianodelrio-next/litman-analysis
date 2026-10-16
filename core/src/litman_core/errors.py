"""Closed set of error codes shared by the ``litman-core`` CLI contract."""
from __future__ import annotations

from pathlib import Path

CORE_ERROR_CODES: tuple[str, ...] = (
    "invalid_config",
    "invalid_input",
    "llm_unavailable",
    "analysis_failed",
    "publication_failed",
    "internal",
)


class CoreError(RuntimeError):
    """Error tagged with one of :data:`CORE_ERROR_CODES` and an optional run path."""

    def __init__(self, code: str, message: str, local_path: Path | None = None) -> None:
        if code not in CORE_ERROR_CODES:
            raise ValueError(f"Código de error desconocido: {code}")
        super().__init__(message)
        self.code = code
        self.message = message
        self.local_path = local_path
