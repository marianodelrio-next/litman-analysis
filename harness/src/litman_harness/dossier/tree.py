"""Inventory of the whole connected tree: breadth-first, only below the root, never into ``_LitMan``."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any
import unicodedata

from .manifest import FOLDER_ROLES
from .models import FOLDER_MIME, Resource

TREE_LIMIT = 2000
LITMAN_FOLDER = "_LitMan"


@dataclass(frozen=True)
class TreeItem:
    resource: Resource
    path: str
    depth: int
    ancestors: tuple[str, ...]  # folder IDs between the root (excluded) and the item

    def json(self) -> dict[str, Any]:
        item = self.resource
        return {"id": item.id, "name": item.name, "mime_type": item.mime_type, "path": self.path,
                "depth": self.depth, "parent_id": self.ancestors[-1] if self.ancestors else None}


def walk_tree(drive: Any, root: Resource, first_level: list[Resource] | None = None,
              limit: int = TREE_LIMIT) -> tuple[list[TreeItem], bool]:
    """All descendants by ``children`` calls on folders of this tree only; returns ``(items, truncated)``."""
    items: list[TreeItem] = []
    queue: deque[tuple[str, str, int, tuple[str, ...], list[Resource] | None]] = deque(
        [(root.id, "", 1, (), first_level)])
    while queue:
        folder_id, prefix, depth, ancestors, known = queue.popleft()
        children = known if known is not None else drive.children(folder_id, root.drive_id)
        for child in sorted(children, key=lambda item: (item.name, item.id)):
            if len(items) >= limit:
                return items, True
            entry = TreeItem(child, f"{prefix}{child.name}", depth, ancestors)
            items.append(entry)
            if child.mime_type == FOLDER_MIME and child.name != LITMAN_FOLDER:
                queue.append((child.id, f"{entry.path}/", depth + 1, (*ancestors, child.id), None))
    return items, False


def _normalized(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    return " ".join("".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower().split())


_STANDARD = {_normalized(label): role for role, label in FOLDER_ROLES}


def suggested_folder_ids(items: list[TreeItem], registered: dict[str, str | None]) -> dict[str, str]:
    """First-level folders named like a standard role; only a suggestion the person confirms.

    Ambiguous names (two folders for one role) and roles already registered get no suggestion.
    """
    matches: dict[str, list[str]] = {}
    taken = {value for value in registered.values() if value}
    for item in items:
        role = _STANDARD.get(_normalized(item.resource.name))
        if (item.depth == 1 and item.resource.mime_type == FOLDER_MIME and role
                and not registered.get(role) and item.resource.id not in taken):
            matches.setdefault(role, []).append(item.resource.id)
    return {role: ids[0] for role, ids in matches.items() if len(ids) == 1}
