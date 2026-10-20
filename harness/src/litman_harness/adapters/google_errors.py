"""Parsing of Google API error bodies shared by the Drive, Docs and Sheets adapters."""
from __future__ import annotations

import json
from typing import Any


def reasons(content: Any) -> set[str]:
    """``error.errors[].reason`` and ``error.details[].reason`` of a Google API error body."""
    try:
        error = json.loads(content.decode("utf-8") if isinstance(content, bytes) else content)["error"]
    except (AttributeError, KeyError, TypeError, ValueError):
        return set()
    if not isinstance(error, dict):
        return set()
    items = [*(error.get("errors") or []), *(error.get("details") or [])]
    return {item["reason"] for item in items if isinstance(item, dict) and isinstance(item.get("reason"), str)}
