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

ROOT = Path(__file__).parents[2]

def test_job_example_matches_public_schema_and_loader() -> None:
    example = ROOT / "examples/jobs/assessment.local.json"
    raw = json.loads(example.read_text(encoding="utf-8"))
    schema = json.loads(resource_path("schemas", "job.schema.json").read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(raw)) == []
    job = load_job(example)
    assert job.job_type is JobType.ASSESSMENT
    assert job.input_kind is StorageKind.LOCAL


def test_job_loader_rejects_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "job.json"
    path.write_text(json.dumps({
        "job_id": "job-1", "job_type": "assessment", "unexpected": True,
        "input": {"kind": "local", "location": "/input"},
        "output": {"kind": "local", "location": "/output"},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="Contrato de job inválido"):
        load_job(path)
def test_summary_artifacts_remain_independent_components() -> None:
    from litman_core.generation.bid_preparation_guide import BidPreparationGuideGenerator
    from litman_core.generation.registry import ARTIFACT_GENERATORS
    from litman_core.generation.technical_summary import TechnicalSummaryGenerator

    root = Path(__file__).resolve().parents[2] / "src" / "litman_core" / "generation"
    assert not (root / "summary").exists()
    assert isinstance(ARTIFACT_GENERATORS["technical-summary"], TechnicalSummaryGenerator)
    assert isinstance(ARTIFACT_GENERATORS["summary"], BidPreparationGuideGenerator)
    assert ARTIFACT_GENERATORS["technical-summary"].id != ARTIFACT_GENERATORS["summary"].id
    assert ARTIFACT_GENERATORS["technical-summary"].filename != ARTIFACT_GENERATORS["summary"].filename
