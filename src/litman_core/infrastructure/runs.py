from __future__ import annotations

import re
import unicodedata
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def case_id(case_dir: Path) -> str:
    return slug(case_dir.name)


def slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "caso"


def new_run_dir(runs_dir: Path, case_dir: Path, stage: str, *, case_name: str | None = None) -> Path:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = runs_dir / slug(case_name) if case_name else runs_dir / case_id(case_dir)
    path = path / stage / run_id
    path.mkdir(parents=True, exist_ok=False)
    for name in ("input", "output", "logs"):
        (path / name).mkdir()
    return path


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
