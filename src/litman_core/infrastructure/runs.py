from __future__ import annotations

import re
import unicodedata
import hashlib
import json
from pathlib import Path


def case_id(case_dir: Path) -> str:
    return slug(case_dir.name)


def slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "caso"


LINEAGE_CONTRACT_VERSION = "dossier-lineage-v1"


def sha256_file(path: Path) -> str:
    """Return the digest of the exact bytes used as an input artifact."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dossier_lineage(*, stage: str, run_dir: Path | None, dossier_path: Path,
                    case_dir: Path, origin: str, parents: list[dict] | None = None) -> dict:
    """Portable provenance for a dossier, independent from the runs layout."""
    return {
        "contract_version": LINEAGE_CONTRACT_VERSION,
        "dossier": {
            "stage": stage,
            "run": {"id": run_dir.name, "path": str(run_dir)} if run_dir else None,
            "file": str(dossier_path),
            "sha256": sha256_file(dossier_path),
            "case": {"id": case_id(case_dir), "path": str(case_dir)},
            "origin": origin,
        },
        "parents": parents or [],
    }


def read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None
