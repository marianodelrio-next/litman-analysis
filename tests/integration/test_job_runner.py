from __future__ import annotations
import json
from pathlib import Path
from types import SimpleNamespace
from litman_core.config import Settings
from litman_core.domain.jobs import JobRequest, JobType, MaterializedCase, StorageKind
from litman_core.execution import JobRunner

def test_runner_executes_in_process_and_cleans_workspace(tmp_path: Path) -> None:
    source = tmp_path / "source"; source.mkdir(); (source / "pliego.md").write_text("# Pliego")
    settings = Settings(project_root=tmp_path, runs_root=tmp_path / "runs", workspace_root=tmp_path / "work", home_dir=tmp_path / "home", codex_home_dir=tmp_path / "codex", codex_preflight=False)
    class Source:
        def materialize(self, request, workspace):
            case = workspace / "case"; case.mkdir(); (case / "pliego.md").write_text("# Pliego"); return MaterializedCase(request.job_id, case)
    class Pipeline:
        def __init__(self, settings, provider): self.settings = settings
        def execute(self, case, *, case_id, bundle, generation=None):
            run = self.settings.runs_dir / case_id / "assessment" / "run"; output = run / "output"; output.mkdir(parents=True)
            (output / "validation.json").write_text(json.dumps({"valid": True})); (output / "result.json").write_text("{}"); (output / "ficha_oportunidad.pdf").write_bytes(b"pdf"); return run, {}
    class Publisher:
        def publish(self, request, run): return (SimpleNamespace(name="ficha_oportunidad.pdf", uri="file://published", checksum="hash"),)
    runner = JobRunner(settings, local_source=Source(), local_publisher=Publisher(), assessment_factory=Pipeline, authentication_factory=lambda **_: object(), provider_factory=lambda **_: object())
    job = JobRequest("job-1", JobType.ASSESSMENT, StorageKind.LOCAL, StorageKind.LOCAL, str(source), str(tmp_path / "out"))
    result = runner.run(job)
    assert result.status == "succeeded" and list((tmp_path / "work").iterdir()) == []
