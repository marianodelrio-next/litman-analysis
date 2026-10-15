"""The single containment rule for the connected dossier tree."""
from __future__ import annotations

from typing import Any

from ..errors import HarnessError
from .models import Resource


def belongs_to_root(drive: Any, root: Resource, item: Resource) -> bool:
    """Prove containment via declared parent IDs only; never search outside the dossier."""
    if item.trashed or item.drive_id != root.drive_id:
        return False
    pending = list(item.parents)
    seen: set[str] = set()
    while pending:
        parent_id = pending.pop()
        if parent_id == root.id:
            return True
        if parent_id in seen:
            continue
        seen.add(parent_id)
        try:
            parent = drive.get(parent_id)
        except (HarnessError, KeyError):
            continue
        if parent.trashed or parent.drive_id != root.drive_id:
            continue
        pending.extend(parent.parents)
    return False
