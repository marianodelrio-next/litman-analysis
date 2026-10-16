import json
from pathlib import Path

import pytest

from litman_core.config import Settings
from litman_core.domain.jobs import JobRequest, JobType, MaterializedCase, StorageKind
from litman_core.errors import CoreError
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


def _settings(tmp_path: Path) -> Settings:
    return Settings(workspace_root=tmp_path / "work", home_dir=tmp_path / "home", codex_home_dir=tmp_path / "codex")


def test_invalid_input_when_case_has_no_documents(tmp_path: Path) -> None:
    source = tmp_path / "source"; source.mkdir()
    settings = _settings(tmp_path)
    job = JobRequest("job-1", JobType.ASSESSMENT, StorageKind.LOCAL, str(source), tmp_path / "out")
    runner = JobRunner(settings, provider_factory=lambda _settings, _job: object())
    with pytest.raises(CoreError) as exc_info:
        runner.run(job)
    assert exc_info.value.code == "invalid_input"
    assert exc_info.value.local_path is not None


def test_llm_unavailable_when_provider_factory_fails(tmp_path: Path) -> None:
    source = tmp_path / "source"; source.mkdir(); (source / "pliego.md").write_text("# Pliego")
    settings = _settings(tmp_path)
    class Source:
        def materialize(self, request, workspace):
            case = workspace / "case"; case.mkdir(); (case / "pliego.md").write_text("# Pliego"); return MaterializedCase(request.job_id, case)
    def provider_factory(_settings, _job):
        raise CoreError("llm_unavailable", "no se encuentra el binario")
    job = JobRequest("job-1", JobType.ASSESSMENT, StorageKind.LOCAL, str(source), tmp_path / "out")
    runner = JobRunner(settings, local_source=Source(), provider_factory=provider_factory)
    with pytest.raises(CoreError) as exc_info:
        runner.run(job)
    assert exc_info.value.code == "llm_unavailable"
    assert exc_info.value.local_path is not None


def test_analysis_failed_when_pipeline_raises(tmp_path: Path) -> None:
    source = tmp_path / "source"; source.mkdir(); (source / "pliego.md").write_text("# Pliego")
    settings = _settings(tmp_path)
    class Source:
        def materialize(self, request, workspace):
            case = workspace / "case"; case.mkdir(); (case / "pliego.md").write_text("# Pliego"); return MaterializedCase(request.job_id, case)
    class Pipeline:
        def __init__(self, settings, provider): pass
        def execute(self, case, *, bundle, run_dir):
            raise RuntimeError("fallo de generación")
    job = JobRequest("job-1", JobType.ASSESSMENT, StorageKind.LOCAL, str(source), tmp_path / "out")
    runner = JobRunner(settings, local_source=Source(), assessment_factory=Pipeline, provider_factory=lambda _settings, _job: object())
    with pytest.raises(CoreError) as exc_info:
        runner.run(job)
    assert exc_info.value.code == "analysis_failed"
    assert exc_info.value.local_path is not None


def test_publication_failed_when_local_publisher_raises(tmp_path: Path) -> None:
    source = tmp_path / "source"; source.mkdir(); (source / "pliego.md").write_text("# Pliego")
    settings = _settings(tmp_path)
    class Source:
        def materialize(self, request, workspace):
            case = workspace / "case"; case.mkdir(); (case / "pliego.md").write_text("# Pliego"); return MaterializedCase(request.job_id, case)
    class Pipeline:
        def __init__(self, settings, provider): pass
        def execute(self, case, *, bundle, run_dir):
            output = run_dir / "output"
            (output / "validation.json").write_text(json.dumps({"valid": True})); (output / "result.json").write_text("{}"); (output / "ficha_oportunidad.pdf").write_bytes(b"pdf")
            return run_dir, {}
    class FailingPublisher:
        def publish(self, run_dir, catalog, *, include_run_files):
            raise RuntimeError("fallo de publicación local")
    job = JobRequest("job-1", JobType.ASSESSMENT, StorageKind.LOCAL, str(source), tmp_path / "out")
    runner = JobRunner(settings, local_source=Source(), local_publisher=FailingPublisher(), assessment_factory=Pipeline, provider_factory=lambda _settings, _job: object())
    with pytest.raises(CoreError) as exc_info:
        runner.run(job)
    assert exc_info.value.code == "publication_failed"
    assert exc_info.value.local_path is not None
