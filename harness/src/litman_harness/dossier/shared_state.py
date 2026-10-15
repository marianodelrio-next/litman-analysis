"""The only authority allowed to commit shared dossier state (manifest and context).

With OAuth the implementation is ``adapters.drive_state.DriveSharedState`` (Drive
v2 ``If-Match``); read-only adapters such as development metadata use
``UnavailableSharedState`` and every apply returns ``pending_concurrency_gate``.
The only version token is the one returned by ``read``.
"""
from __future__ import annotations

from typing import Protocol

from ..errors import HarnessError
from .models import Resource


class SharedStateCapability(Protocol):
    available: bool

    def create_if_absent(self, name: str, parent_id: str, content: str, operation_id: str,
                         action_id: str) -> Resource:
        """Create once; a retry with the same markers returns the existing file."""

    def read(self, file_id: str) -> tuple[str, str]:
        """Return ``(content, version)``."""

    def update_if_version(self, file_id: str, content: str, expected_version: str, operation_id: str) -> Resource:
        """Atomic compare-and-swap; raises ``HarnessError("concurrent_change")`` on mismatch."""


class UnavailableSharedState:
    """Read-only configurations (development metadata): no shared write is possible."""
    available = False

    def create_if_absent(self, *args, **kwargs):
        raise HarnessError("pending_concurrency_gate", "El adaptador configurado no escribe estado compartido")

    def read(self, *args, **kwargs):
        raise HarnessError("pending_concurrency_gate", "El adaptador configurado no escribe estado compartido")

    def update_if_version(self, *args, **kwargs):
        raise HarnessError("pending_concurrency_gate", "El adaptador configurado no escribe estado compartido")
