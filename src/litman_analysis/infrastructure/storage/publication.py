"""Identifiers for customer-facing publication folders."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable


def publication_folder_name(
    job_id: str,
    *,
    now: Callable[[], datetime] | None = None,
) -> str:
    """Return a human-sortable, unique name without changing the logical job ID."""
    instant = (now or (lambda: datetime.now(timezone.utc)))()
    timestamp = instant.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"{job_id}-{timestamp}"
