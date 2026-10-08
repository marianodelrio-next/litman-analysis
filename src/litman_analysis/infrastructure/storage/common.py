from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_SHA256 = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class CatalogArtifact:
    source: Path
    name: str
    checksum: str


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_checksum(value: str) -> str:
    if not _SHA256.fullmatch(value):
        raise ValueError("checksum debe ser SHA-256 hexadecimal de 64 caracteres (opcional sha256:)")
    return value.removeprefix("sha256:").lower()


def safe_filename(value: str) -> str:
    name = Path(value).name
    if name != value or not name or name in {".", ".."}:
        raise ValueError(f"Nombre de documento inválido: {value!r}")
    return name


def publication_catalog(run_dir: Path) -> tuple[CatalogArtifact, ...]:
    """Only permanent public artifacts; never input, logs, secrets or temporaries."""
    files: list[CatalogArtifact] = []
    output = run_dir / "output"
    if output.is_dir():
        for path in sorted(output.rglob("*")):
            if path.is_file():
                files.append(CatalogArtifact(path, path.relative_to(run_dir).as_posix(), sha256(path)))
    lineage = run_dir / "lineage.json"
    if lineage.is_file():
        files.append(CatalogArtifact(lineage, "lineage.json", sha256(lineage)))
    return tuple(files)


_DETAILED_ANALYSIS_DELIVERABLES = ("resumen.docx",)


def detailed_analysis_delivery_catalog(run_dir: Path) -> tuple[CatalogArtifact, ...]:
    """The closed, flat public delivery contract for detailed analysis.

    Run directories deliberately contain diagnostics and intermediate files.  They
    must never become part of the customer-facing Drive delivery.
    """
    output = run_dir / "output"
    artifacts: list[CatalogArtifact] = []
    names = list(_DETAILED_ANALYSIS_DELIVERABLES)
    manifest_path = output / "generation_manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("generation_manifest.json no es legible o contiene JSON inválido") from exc
        if not isinstance(manifest, dict) or not isinstance(manifest.get("artifacts"), list):
            raise ValueError("generation_manifest.json no contiene una lista de artefactos válida")
        if not all(isinstance(item, dict) for item in manifest["artifacts"]):
            raise ValueError("generation_manifest.json contiene artefactos inválidos")
        technical = [item for item in manifest["artifacts"] if item.get("id") == "technical-document"]
        if len(technical) != 1 or not isinstance(technical[0].get("documents"), list):
            raise ValueError("generation_manifest.json debe declarar exactamente un artefacto technical-document")
        declared = [Path(path).name for path in technical[0]["documents"] if str(path).lower().endswith(".docx")]
        if len(declared) != 1 or declared[0] == "resumen.docx":
            raise ValueError("generation_manifest.json debe declarar exactamente un DOCX técnico")
        names.extend(declared)
    if not any(name.lower().endswith(".docx") and name != "resumen.docx" for name in names):
        # Compatibilidad con runs previos; no reconstruye un nombre nuevo.
        names.append("propuesta_tecnica_base.docx")
    names.append("simulador_economico.xlsx")
    for name in dict.fromkeys(names):
        path = output / name
        if not path.is_file():
            raise ValueError(f"No existe el artefacto de entrega requerido: {path}")
        artifacts.append(CatalogArtifact(path, name, sha256(path)))
    return tuple(artifacts)


def catalog_digest(catalog: Iterable[CatalogArtifact]) -> str:
    """Stable digest of the public contract, independent of filesystem order."""
    digest = hashlib.sha256()
    for item in sorted(catalog, key=lambda artifact: artifact.name):
        digest.update(item.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.checksum.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def manifest(job_id: str, job_type: str, artifacts: Iterable[tuple[str, str, str]]) -> dict:
    return {"schema_version": 1, "job_id": job_id, "job_type": str(job_type),
            "artifacts": [{"name": n, "sha256": h, "uri": u} for n, h, u in artifacts]}


def write_manifest(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def compatible_manifest(value: object, job_id: str, job_type: str, catalog: tuple[CatalogArtifact, ...]) -> bool:
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        return False
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, list):
        return False
    actual: dict[str, str] = {}
    for item in artifacts:
        if not isinstance(item, dict):
            return False
        name, checksum, uri = item.get("name"), item.get("sha256"), item.get("uri")
        if not isinstance(name, str) or not isinstance(checksum, str) or not isinstance(uri, str):
            return False
        if name in actual:
            return False
        actual[name] = checksum.lower()
    expected = {item.name: item.checksum for item in catalog}
    return (
        value.get("job_id") == job_id
        and value.get("job_type") == str(job_type)
        and actual == expected
    )
