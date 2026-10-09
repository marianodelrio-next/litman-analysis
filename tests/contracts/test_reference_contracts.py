import json
from pathlib import Path

from contract_descriptor import semantic_descriptor


ROOT = Path(__file__).parents[1]


def test_reference_jobs_are_executable_contract_shapes() -> None:
    fixtures = Path(__file__).parents[1] / "fixtures/reference-jobs"
    jobs = [json.loads(path.read_text()) for path in sorted(fixtures.glob("*.json"))]
    assert {job["job_type"] for job in jobs} == {"assessment", "detailed-analysis"}
    assert all(set(job) >= {"job_id", "job_type", "input", "output"} for job in jobs)


def test_descriptor_ignores_ephemeral_metadata_but_hashes_execution_bytes(tmp_path: Path) -> None:
    first = tmp_path / "result.json"
    first.write_bytes(b"stable result")
    a = semantic_descriptor({"timestamp": "2026-10-09T10:00:00Z", "uri": "drive://abc", "value": "same"}, [first])
    first.write_bytes(b"changed result")
    b = semantic_descriptor({"timestamp": "2026-10-09T11:00:00Z", "uri": "drive://def", "value": "same"}, [first])
    assert a["semantic"] == b["semantic"]
    assert a["files"] != b["files"]
