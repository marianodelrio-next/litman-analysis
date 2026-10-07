from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from litman_analysis.application.ports.llm import LLMProvider
from litman_analysis.infrastructure.runs import dossier_lineage, new_run_dir, read_json, sha256_file

from .registry import ARTIFACT_GENERATORS, resolve_artifact_generators
from .models import ArtifactContext, ArtifactGenerator
from .opportunity_report import generate_opportunity_report


def generate_documents(dossier_path: Path, output_dir: Path | None = None,
                       artifacts: list[str] | None = None, provider: LLMProvider | None = None,
                       template_id: str = "next-standard-v1", economic_template_id: str = "standard-v1",
                       include_internal_pending: bool = True, output_language: str = "auto",
                       content_profile: str = "skeleton-v1") -> dict:
    dossier_path = dossier_path.resolve()
    dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
    lineage = _resolve_dossier_lineage(dossier_path)
    source = lineage["dossier"]
    case = source["case"]
    case_root = Path(case["path"])
    source_run = Path(source["run"]["path"]) if source.get("run") else None
    run_dir = output_dir or new_run_dir(case_root.parent, case_root, "generation")
    _ensure_layout(run_dir)
    snapshot = run_dir / "input" / "dossier.json"
    shutil.copy2(dossier_path, snapshot)
    context = ArtifactContext(dossier=dossier, run_dir=run_dir, source_run=source_run, case_dir=case_root,
        template_id=template_id, economic_template_id=economic_template_id,
        include_internal_pending=include_internal_pending, output_language=output_language,
        content_profile=content_profile, provider=provider)
    results = [_generate(generator, context) for generator in resolve_artifact_generators(artifacts)]
    # El snapshot conserva exactamente la entrada utilizada para generar los entregables.
    output_lineage = dict(lineage)
    output_lineage["input_snapshot"] = str(snapshot)
    output_lineage["input_snapshot_sha256"] = sha256_file(snapshot)
    manifest = _manifest(snapshot, source_run, run_dir, content_profile, results, output_lineage)
    _write_json(run_dir / "output" / "generation_manifest.json", manifest)
    _write_json(run_dir / "lineage.json", output_lineage)
    return manifest


def render_existing_run(run_dir: Path, *, include_internal_pending: bool = True,
                        refresh_skeleton: bool = False) -> dict:
    generator = ARTIFACT_GENERATORS["technical-document"]
    try:
        return generator.rerender(run_dir.resolve(), include_internal_pending=include_internal_pending,
                                  refresh_skeleton=refresh_skeleton)
    except Exception as error:
        raise ValueError(f"Error al rerenderizar el artefacto '{generator.id}': {error}") from error


def _generate(generator: ArtifactGenerator, context: ArtifactContext) -> dict:
    try:
        return generator.generate(context)
    except Exception as error:
        raise ValueError(f"Error al generar el artefacto '{generator.id}': {error}") from error


def _manifest(snapshot: Path, source_run: Path | None, run_dir: Path, content_profile: str,
              results: list[dict], lineage: dict) -> dict:
    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(), "dossier_path": str(snapshot),
        "source_run": str(source_run) if source_run else None, "run_dir": str(run_dir), "content_profile": content_profile,
        "lineage": lineage,
        "documents": [path for item in results for path in item["documents"]],
        "pending_count": sum(len(item["pending"]) for item in results), "artifacts": results}
    for item in results:
        manifest.update(item["metadata"].get("manifest_fields", {}))
    return manifest


def _ensure_layout(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in ("input", "output", "logs"): (run_dir / name).mkdir(exist_ok=True)


def _resolve_dossier_lineage(dossier_path: Path) -> dict:
    """Resuelve el origen declarado o trata el dossier como entrada externa."""
    # El contrato publica lineage en el directorio del run. Limitar la búsqueda
    # a ese borde evita adoptar metadata ajena de un ancestro de almacenamiento.
    for directory in (dossier_path.parent, dossier_path.parent.parent):
        metadata = read_json(directory / "lineage.json")
        if metadata and isinstance(metadata.get("dossier"), dict):
            source = metadata["dossier"]
            declared_file = source.get("file")
            if not isinstance(declared_file, str) or Path(declared_file).resolve() != dossier_path:
                continue
            if source.get("sha256"):
                actual = sha256_file(dossier_path)
                if source["sha256"] != actual:
                    raise ValueError("El hash SHA-256 del dossier no coincide con el declarado en lineage.json")
            if source.get("case", {}).get("path"):
                return metadata

    # Imported dossiers are valid inputs too.  The enclosing directory is a local case anchor
    # only when the caller did not provide an explicit output directory.
    return dossier_lineage(stage="external", run_dir=None, dossier_path=dossier_path,
                           case_dir=dossier_path.parent, origin="external")


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
