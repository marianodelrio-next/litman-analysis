"""Original selection rules and stable, verified downloads into a private workspace."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..dossier.membership import belongs_to_root
from ..dossier.models import Resource
from ..errors import HarnessError
from ..plans.models import Plan

NATIVE_PREFIX = "application/vnd.google-apps."
ALLOWED_MIME_TYPES = frozenset({
    "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel", "text/plain",
})


def _digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    return _digest(path, "sha256")


def md5_file(path: Path) -> str:
    """Comparable with Drive's ``md5Checksum`` of the downloaded bytes."""
    return _digest(path, "md5")


def require_checksum(item: Resource) -> str:
    """Content identity of an original; Drive ``version`` changes without content changes."""
    if not item.md5_checksum:
        raise HarnessError("missing_checksum", "Drive no informa el MD5 de este original; no se puede verificar "
                           "que su contenido no cambie", details={"id": item.id})
    return item.md5_checksum


def validate_original(drive: Any, root: Resource, item: Resource) -> None:
    if not belongs_to_root(drive, root, item):
        raise HarnessError("outside_expediente",
                           "El original debe pertenecer a la raíz y unidad compartida del expediente")
    if item.capabilities and not item.capabilities.get("canDownload", False):
        raise HarnessError("insufficient_capability", "La cuenta activa no puede descargar un original")
    if item.mime_type.startswith(NATIVE_PREFIX):
        raise HarnessError("native_google_file", "Los originales nativos de Google no se exportan implícitamente")
    if item.mime_type not in ALLOWED_MIME_TYPES:
        raise HarnessError("unsupported_mime", f"Formato no admitido: {item.mime_type}")


def _stale(identifier: str, during_download: bool) -> HarnessError:
    message = "El original cambió durante la descarga" if during_download \
        else "Un original cambió antes de ejecutar Core"
    return HarnessError("stale_plan", message, details={"file_id": identifier})


def verify_originals(drive: Any, root: Resource, plan: Plan, *, during_download: bool = False) -> None:
    """Every planned original must keep its MD5, stay in the tree and remain downloadable."""
    for action in plan.actions:
        if action.kind != "download_original" or not action.resource_id:
            continue
        current = drive.get(action.resource_id)
        if current.trashed or current.md5_checksum != action.expected_version:
            raise _stale(action.resource_id, during_download)
        validate_original(drive, root, current)


def download_originals(drive: Any, root: Resource, plan: Plan, inputs_dir: Path) -> list[dict[str, Any]]:
    """Download the planned originals and fail if any changed while downloading."""
    snapshot = []
    for action in plan.actions:
        if action.kind != "download_original" or not action.resource_id:
            continue
        target = inputs_dir / f"{action.resource_id}-{Path(action.name).name}"
        drive.download(action.resource_id, target)
        md5 = md5_file(target)
        if md5 != action.expected_version:
            raise _stale(action.resource_id, True)
        snapshot.append({"file_id": action.resource_id, "name": action.name,
                         "drive_version": action.metadata.get("drive_version"), "md5_checksum": md5,
                         "sha256": sha256_file(target), "size": target.stat().st_size})
    verify_originals(drive, root, plan, during_download=True)
    return snapshot
