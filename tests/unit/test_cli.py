import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from litman_core import cli, JobRunner
from litman_core.domain.jobs import JobType

@pytest.mark.parametrize("command,expected", [("assess", JobType.ASSESSMENT), ("analyze", JobType.DETAILED_ANALYSIS)])
def test_cli_wrappers_use_runner_and_normalize_artifacts(tmp_path, monkeypatch, capsys, command, expected):
    case = tmp_path / "case"; case.mkdir()
    seen = []
    class Runner:
        def run(self, job):
            seen.append(job)
            return SimpleNamespace(job_id=job.job_id, status="succeeded", run_dir=Path("/runs"), diagnostics_dir=Path("/runs"),
                                   artifacts=(SimpleNamespace(name="ficha_oportunidad.pdf", uri="file:///published/ficha.pdf", checksum="a" * 64),))
    monkeypatch.setattr(cli, "JobRunner", Runner)
    cli.main([command, str(case), "--output", str(tmp_path / "out")])
    payload = json.loads(capsys.readouterr().out)
    assert seen[0].job_type is expected
    assert payload["artifacts"] == [{"name": "ficha_oportunidad.pdf", "uri": "file:///published/ficha.pdf", "checksum": "a" * 64}]

def test_cli_run_uses_loaded_job(tmp_path, monkeypatch, capsys):
    source = tmp_path / "case"; source.mkdir()
    job = tmp_path / "job.json"
    job.write_text(json.dumps({"job_id":"run-id","job_type":"assessment","input":{"kind":"local","location":str(source)},"output":{"kind":"local","location":str(tmp_path/"out")}}))
    seen = []
    class Runner:
        def run(self, request):
            seen.append(request)
            return SimpleNamespace(job_id="run-id", status="succeeded", run_dir=Path("/run"), diagnostics_dir=Path("/run"), artifacts=())
    monkeypatch.setattr(cli, "JobRunner", Runner)
    cli.main(["run", str(job)])
    assert seen[0].job_id == "run-id" and json.loads(capsys.readouterr().out)["status"] == "succeeded"


def test_cli_run_and_analyze_apply_explicit_config(tmp_path, monkeypatch, capsys):
    config = tmp_path / "config.toml"
    config.write_text('[analysis.detailed.generation]\nartifacts=["technical-summary"]\n', encoding="utf-8")
    case = tmp_path / "case"
    case.mkdir()
    job = tmp_path / "job.json"
    job.write_text(json.dumps({"job_id":"run-id","job_type":"detailed-analysis","input":{"kind":"local","location":str(case)},"output":{"kind":"local","location":str(tmp_path/"out")}}))
    seen = []
    class Runner:
        def run(self, request):
            seen.append(request)
            return SimpleNamespace(job_id=request.job_id, status="succeeded", run_dir=Path("/run"), diagnostics_dir=Path("/run"), artifacts=())
    monkeypatch.setattr(cli, "JobRunner", Runner)
    cli.main(["run", str(job), "--config", str(config)])
    cli.main(["analyze", str(case), "--config", str(config)])
    capsys.readouterr()
    assert seen[0].options["generation"]["artifacts"] == ["technical-summary"]
    assert seen[1].options["generation"]["artifacts"] == ["technical-summary"]

def test_cli_rejects_native_and_emits_json_failure(tmp_path, monkeypatch, capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["assess", str(tmp_path), "--native"])
    assert error.value.code == 2
    class Runner:
        def run(self, _job): raise ValueError("bad job")
    monkeypatch.setattr(cli, "JobRunner", Runner)
    with pytest.raises(SystemExit) as error:
        cli.main(["assess", str(tmp_path)])
    assert error.value.code == 1
    captured = capsys.readouterr()
    assert json.loads(captured.err.splitlines()[-1])["status"] == "failed"
