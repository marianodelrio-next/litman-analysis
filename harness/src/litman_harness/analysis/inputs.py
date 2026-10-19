"""Original selection rules and stable, verified downloads into a private workspace."""
from __future__ import annotations

import hashlib
import platform
from pathlib import Path
import re
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
WINDOWS_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED = frozenset({"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                              *(f"LPT{i}" for i in range(1, 10))})
WINDOWS_COMPONENT_LIMIT = 120
# A longer suffix after the last dot is part of the document name, not an extension.
MAX_EXTENSION = 10
# Keep a margin below the traditional 260-character Windows path limit for
# directories Core creates below the input/output locations.
WINDOWS_PATH_LIMIT = 260
CORE_PATH_MARGIN = 60


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


def _windows_local_name(file_id: str, name: str, limit: int = WINDOWS_COMPONENT_LIMIT) -> str:
    """A traceable Windows component which keeps useful document-name clues."""
    # Drive names are labels, not paths: retain all words around either separator.
    visible = name
    visible = WINDOWS_INVALID.sub("_", visible).rstrip(". ")
    if not visible:
        visible = "original"
    stem, dot, suffix = visible.rpartition(".")
    if not dot or not stem or len(suffix) > MAX_EXTENSION:
        stem, suffix = visible, ""
    stem = stem.rstrip(". ") or "original"
    if stem.upper() in WINDOWS_RESERVED:
        stem = f"_{stem}"
    suffix = WINDOWS_INVALID.sub("_", suffix).rstrip(". ")
    extension = f".{suffix}" if suffix else ""
    prefix = f"{file_id}-"
    # Only the stem is truncated; a single character is kept so callers can detect an impossible fit.
    available = max(1, limit - len(prefix) - len(extension))
    return f"{prefix}{stem[:available].rstrip('. ') or 'original'[:available]}{extension}"


def local_original_name(file_id: str, name: str, limit: int = WINDOWS_COMPONENT_LIMIT) -> str:
    """Return the local filename without changing the original Drive name.

    On Windows the name fits in ``limit`` characters when possible; POSIX ignores it.
    """
    if platform.system() == "Windows":
        return _windows_local_name(file_id, name, limit)
    return f"{file_id}-{Path(name).name}"


def _download_targets(plan: Plan, inputs_dir: Path) -> list[tuple[Any, Path, str]]:
    targets: list[tuple[Any, Path, str]] = []
    seen: set[str] = set()
    # The component budget left below the actual input directory (minus the separator).
    budget = WINDOWS_PATH_LIMIT - CORE_PATH_MARGIN - len(str(inputs_dir)) - 1
    limit = min(WINDOWS_COMPONENT_LIMIT, budget)
    for action in plan.actions:
        if action.kind != "download_original" or not action.resource_id:
            continue
        local_name = local_original_name(action.resource_id, action.name, limit)
        target = inputs_dir / local_name
        key = local_name.casefold()
        if key in seen:
            raise HarnessError("local_name_collision", "Dos originales producirían la misma copia local")
        seen.add(key)
        if platform.system() == "Windows" and len(str(target)) + CORE_PATH_MARGIN > WINDOWS_PATH_LIMIT:
            raise HarnessError("work_path_too_long", "La ruta de trabajo es demasiado larga; configure "
                               "LITMAN_HARNESS_WORK_DIR con una ruta más corta")
        targets.append((action, target, local_name))
    return targets


def download_originals(drive: Any, root: Resource, plan: Plan, inputs_dir: Path) -> list[dict[str, Any]]:
    """Download the planned originals and fail if any changed while downloading."""
    snapshot = []
    # Derive and validate every destination before the first network write.
    for action, target, local_name in _download_targets(plan, inputs_dir):
        drive.download(action.resource_id, target)
        md5 = md5_file(target)
        if md5 != action.expected_version:
            raise _stale(action.resource_id, True)
        snapshot.append({"file_id": action.resource_id, "name": action.name, "local_name": local_name,
                         "drive_version": action.metadata.get("drive_version"), "md5_checksum": md5,
                         "sha256": sha256_file(target), "size": target.stat().st_size})
    verify_originals(drive, root, plan, during_download=True)
    return snapshot
