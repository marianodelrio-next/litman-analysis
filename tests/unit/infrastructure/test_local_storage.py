from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from litman_core.application.job_loader import load_job
from litman_core.config import Settings
from litman_core.domain.jobs import JobRequest, JobType, StorageKind
from litman_core.infrastructure.storage.local import LocalArtifactPublisher, LocalDocumentSource
from litman_core.resource_paths import resource_path

ROOT = Path(__file__).parents[3]

def local_job(input_dir: Path, output_dir: Path) -> JobRequest:
    return JobRequest(
        job_id="job-1", job_type=JobType.ASSESSMENT,
        input_kind=StorageKind.LOCAL, output_kind=StorageKind.LOCAL,
        input_location=str(input_dir), output_location=str(output_dir),
    )
def test_local_source_materializes_an_isolated_copy(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "PCAP.txt").write_text("original", encoding="utf-8")
    materialized = LocalDocumentSource().materialize(
        local_job(source, tmp_path / "published"), tmp_path / "workspace")
    (materialized.directory / "PCAP.txt").write_text("changed", encoding="utf-8")
    assert (source / "PCAP.txt").read_text(encoding="utf-8") == "original"


def test_local_publisher_publishes_only_public_assessment_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    output = tmp_path / "published"
    run = tmp_path / "run"
    (run / "output").mkdir(parents=True)
    payload = b"pdf"
    (run / "output" / "ficha_oportunidad.pdf").write_bytes(payload)
    (run / "lineage.json").write_text("{}")
    published = LocalArtifactPublisher(publication_name_factory=lambda _: "job-1-20261008T153045.123456Z").publish(local_job(source, output), run)
    assert (output / "job-1-20261008T153045.123456Z" / "ficha_oportunidad.pdf").read_bytes() == payload
    assert not (output / "job-1-20261008T153045.123456Z" / "lineage.json").exists()
    item = next(value for value in published if value.name == "ficha_oportunidad.pdf")
    assert item.checksum == hashlib.sha256(payload).hexdigest()


def test_local_publication_creates_a_new_folder_for_each_execution(tmp_path: Path) -> None:
    source, output, run = tmp_path / "source", tmp_path / "published", tmp_path / "run"
    source.mkdir()
    run.mkdir()
    (run / "output").mkdir()
    (run / "output" / "ficha_oportunidad.pdf").write_bytes(b"pdf")
    job = local_job(source, output)
    names = iter(("job-1-20261008T153045.123456Z", "job-1-20261008T153046.123456Z"))
    publisher = LocalArtifactPublisher(publication_name_factory=lambda _: next(names))
    publisher.publish(job, run)
    publisher.publish(job, run)
    folders = sorted(path.name for path in output.iterdir())
    assert folders == list(names := ["job-1-20261008T153045.123456Z", "job-1-20261008T153046.123456Z"])
    assert all((output / folder / "ficha_oportunidad.pdf").is_file() for folder in folders)



def test_settings_can_separate_runtime_data_from_project(tmp_path: Path) -> None:
    settings = Settings(project_root=ROOT, runs_root=tmp_path / "runs",
                        workspace_root=tmp_path / "workspace")
    assert settings.runs_dir == tmp_path / "runs"
    assert settings.workspace_dir == tmp_path / "workspace"

def test_local_detailed_publication_is_flat_and_excludes_internal_files(tmp_path: Path) -> None:
    source, output, run = tmp_path / "source", tmp_path / "published", tmp_path / "run"
    source.mkdir(); (run / "output").mkdir(parents=True)
    for name, data in (("resumen_tecnico.docx", b"technical"), ("guia_preparacion_oferta.docx", b"guide"),
                       ("propuesta_tecnica_base.docx", b"proposal"), ("simulador_economico.xlsx", b"xlsx")):
        (run / "output" / name).write_bytes(data)
    (run / "output" / "generation_manifest.json").write_text(json.dumps({"artifacts":[
        {"id":"technical-summary","documents":["resumen_tecnico.docx"]},
        {"id":"summary","documents":["guia_preparacion_oferta.docx"]},
        {"id":"technical-document","documents":["propuesta_tecnica_base.docx"]}]}))
    (run / "output" / "result.json").write_text("{}"); (run / "lineage.json").write_text("{}")
    job = JobRequest("job-1", JobType.DETAILED_ANALYSIS, StorageKind.LOCAL, StorageKind.LOCAL, str(source), str(output))
    publication_id = "job-1-20261008T153045.123456Z"
    published = LocalArtifactPublisher(publication_name_factory=lambda _: publication_id).publish(job, run)
    assert {item.name for item in published} == {"resumen_tecnico.docx", "guia_preparacion_oferta.docx", "propuesta_tecnica_base.docx", "simulador_economico.xlsx"}
    assert not list((output / publication_id).glob("*.json"))
