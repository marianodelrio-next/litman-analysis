"""The single containment rule for the connected dossier tree."""
from __future__ import annotations

from typing import Any

from ..errors import HarnessError
from .models import Resource
from .tree import LITMAN_FOLDER


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


def in_litman(drive: Any, root: Resource, item: Resource) -> bool:
    """Whether the item is ``_LitMan`` itself or sits anywhere below a ``_LitMan`` folder of the tree."""
    if item.name == LITMAN_FOLDER:
        return True
    pending = list(item.parents)
    seen: set[str] = set()
    while pending:
        parent_id = pending.pop()
        if parent_id == root.id or parent_id in seen:
            continue
        seen.add(parent_id)
        try:
            parent = drive.get(parent_id)
        except HarnessError:
            continue
        if parent.name == LITMAN_FOLDER:
            return True
        pending.extend(parent.parents)
    return False
