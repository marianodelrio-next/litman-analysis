import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator
from litman_core.application.job_loader import load_job
from litman_core.domain.jobs import JobRequest
from litman_core.resource_paths import resource_path

ROOT = Path(__file__).parents[1]

def test_drive_example_and_all_examples_validate():
    schema = json.loads(resource_path("schemas", "job.schema.json").read_text())
    validator = Draft202012Validator(schema)
    for path in (ROOT / "examples/jobs").glob("*.json"):
        assert list(validator.iter_errors(json.loads(path.read_text()))) == []

def test_drive_without_documents_loads(tmp_path):
    path = tmp_path / "job.json"
    path.write_text(json.dumps({"job_id":"a", "job_type":"assessment", "input":{"kind":"google-drive","location":"x"}, "output":{"kind":"local","location":"x"}}))
    assert load_job(path).input_location == "x"

def test_schema_rejects_old_documents_and_request_has_no_documents(tmp_path):
    path = tmp_path / "job.json"
    path.write_text(json.dumps({"job_id":"a", "job_type":"assessment", "input":{"kind":"google-drive","location":"x", "documents":[]}, "output":{"kind":"local","location":"x"}}))
    with pytest.raises(ValueError, match="Contrato de job inválido"):
        load_job(path)
    assert "documents" not in JobRequest.__dataclass_fields__
