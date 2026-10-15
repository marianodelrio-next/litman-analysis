import json
from pathlib import Path

from litman_core.config import Settings
from litman_core.domain.jobs import JobRequest, JobType, MaterializedCase, StorageKind
from litman_core.execution import JobRunner


def test_runner_uses_allocated_flat_run_and_cleans_workspace(tmp_path: Path) -> None:
    source = tmp_path / "source"; source.mkdir(); (source / "pliego.md").write_text("# Pliego")
    settings = Settings(workspace_root=tmp_path / "work", home_dir=tmp_path / "home", codex_home_dir=tmp_path / "codex")
    class Source:
        def materialize(self, request, workspace):
            case = workspace / "case"; case.mkdir(); (case / "pliego.md").write_text("# Pliego"); return MaterializedCase(request.job_id, case)
    class Pipeline:
        def __init__(self, settings, provider): pass
        def execute(self, case, *, bundle, run_dir):
            output = run_dir / "output"
            (output / "validation.json").write_text(json.dumps({"valid": True})); (output / "result.json").write_text("{}"); (output / "ficha_oportunidad.pdf").write_bytes(b"pdf")
            return run_dir, {}
    job = JobRequest("job-1", JobType.ASSESSMENT, StorageKind.LOCAL, str(source), tmp_path / "out")
    runner = JobRunner(settings, local_source=Source(), assessment_factory=Pipeline, provider_factory=lambda _settings, _job: object())
    result = runner.run(job)
    assert result.status == "succeeded" and result.local_path.parent == tmp_path / "out"
    assert list((tmp_path / "work").iterdir()) == []
