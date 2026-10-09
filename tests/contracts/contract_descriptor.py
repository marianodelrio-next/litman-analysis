"""Semantic comparison helpers for deterministic contract tests."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

_VOLATILE = re.compile(r"(?:/|[A-Za-z]:\\)[^\s\"']+|\b\d{8}T\d{6}(?:\.\d+)?Z\b|[0-9a-f]{32,}", re.I)


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in sorted(value.items()) if key not in {"timestamp", "created_at", "uri", "run_id"}}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, str):
        return _VOLATILE.sub("<volatile>", value)
    return value


def semantic_descriptor(value: dict[str, Any], files: list[Path] = ()) -> dict[str, Any]:
    return {"semantic": _normalize(value), "files": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)}}
