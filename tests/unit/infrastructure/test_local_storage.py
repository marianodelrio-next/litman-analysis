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


def test_local_publisher_copies_run_and_reports_checksums(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    output = tmp_path / "published"
    run = tmp_path / "run"
    (run / "output").mkdir(parents=True)
    payload = b'{"valid": true}'
    (run / "output" / "result.json").write_bytes(payload)
    published = LocalArtifactPublisher(publication_name_factory=lambda _: "job-1-20261008T153045.123456Z").publish(local_job(source, output), run)
    assert (output / "job-1-20261008T153045.123456Z" / "output" / "result.json").read_bytes() == payload
    item = next(value for value in published if value.name == "output/result.json")
    assert item.checksum == hashlib.sha256(payload).hexdigest()


def test_local_publication_creates_a_new_folder_for_each_execution(tmp_path: Path) -> None:
    source, output, run = tmp_path / "source", tmp_path / "published", tmp_path / "run"
    source.mkdir()
    run.mkdir()
    job = local_job(source, output)
    names = iter(("job-1-20261008T153045.123456Z", "job-1-20261008T153046.123456Z"))
    publisher = LocalArtifactPublisher(publication_name_factory=lambda _: next(names))
    publisher.publish(job, run)
    publisher.publish(job, run)
    folders = sorted(path.name for path in output.iterdir())
    assert folders == ["job-1-20261008T153045.123456Z", "job-1-20261008T153046.123456Z"]
    assert all(json.loads((output / folder / "publication-manifest.json").read_text())["job_id"] == "job-1" for folder in folders)



def test_settings_can_separate_runtime_data_from_project(tmp_path: Path) -> None:
    settings = Settings(project_root=ROOT, runs_root=tmp_path / "runs",
                        workspace_root=tmp_path / "workspace")
    assert settings.runs_dir == tmp_path / "runs"
    assert settings.workspace_dir == tmp_path / "workspace"
