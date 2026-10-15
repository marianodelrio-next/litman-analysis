"""Stable errors exposed by every harness transport."""
from __future__ import annotations

import os
import re
from typing import Any

_SECRET_PATTERNS = (re.compile(r"ya29\.[A-Za-z0-9._-]+"), re.compile(r"1//[A-Za-z0-9._-]+"),
                    re.compile(r"[^\s'\"]*token[^\s'\"]*\.json", re.IGNORECASE),
                    re.compile(r"[^\s'\"]*client_secret[^\s'\"]*\.json", re.IGNORECASE))


class HarnessError(ValueError):
    """Stable, JSON-safe harness failure with a machine readable code."""

    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def safe_exception_message(exc: BaseException, limit: int = 300) -> str:
    """Truncated description of an unexpected error without environment values or token paths."""
    message = f"{type(exc).__name__}: {exc}"
    for name, value in os.environ.items():
        if name.startswith(("LITMAN_HARNESS_", "GOOGLE_")) and len(value) >= 4:
            message = message.replace(value, "[redactado]")
    for pattern in _SECRET_PATTERNS:
        message = pattern.sub("[redactado]", message)
    return message[:limit]
