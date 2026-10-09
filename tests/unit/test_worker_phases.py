import json
import stat
from pathlib import Path
from types import SimpleNamespace
import pytest, yaml
from litman_core import worker
from litman_core.config import Settings
from litman_core.execution import JobRunnerResult

def test_worker_exposes_only_run_and_preflight(capsys):
    with pytest.raises(SystemExit): worker.main(["--help"])
    value=capsys.readouterr().out; assert "run" in value and "preflight" in value and "prepare" not in value and "publish" not in value
def test_worker_run_emits_json(tmp_path,monkeypatch,capsys):
    path=tmp_path/"job.json"; path.write_text(json.dumps({"job_id":"x","job_type":"assessment","input":{"kind":"local","location":"/input"},"output":{"kind":"local","location":"/output"}}))
    class Runner:
        def __init__(self,*a,**k): pass
        def run(self,j): return JobRunnerResult("x","succeeded",Path("/data/runs/x"),Path("/data/runs/x"),())
    monkeypatch.setattr(worker,"JobRunner",Runner); worker.main(["run",str(path)])
    assert json.loads(capsys.readouterr().out)["status"]=="succeeded"
def test_compose_has_one_unified_hardened_service():
    compose=yaml.safe_load((Path(__file__).parents[2]/"compose.yaml").read_text()); assert set(compose["services"])=={"litman-analysis"}
    service=compose["services"]["litman-analysis"]; volumes=" ".join(service["volumes"])
    assert service["read_only"] is True and service["cap_drop"]==["ALL"] and ":/input:ro" in volumes and ":/output" in volumes and ":/data/runs" in volumes and ":/run/secrets:ro" in volumes and ":/var/lib/litman-analysis/codex" in volumes
    assert "cap_add" not in service and "privileged" not in service
    assert service["security_opt"] == ["no-new-privileges:true"]

def test_image_has_no_nested_privilege_binary():
    dockerfile=(Path(__file__).parents[2]/"Dockerfile").read_text().lower()
    assert "bubblewrap" not in dockerfile and "bwrap" not in dockerfile
    assert "chromium" in dockerfile and "ripgrep" in dockerfile and "@openai/codex@${codex_version}" in dockerfile
    assert 'entrypoint ["litman-core-worker"]' in dockerfile

def test_container_preflight_exercises_codex_in_container(tmp_path,monkeypatch):
    input_dir=tmp_path/"input"; input_dir.mkdir(); (input_dir/"fixture.md").write_text("fixture")
    codex_home=tmp_path/"codex"; codex_home.mkdir(); auth=codex_home/"auth.json"; auth.write_text("{}")
    auth.chmod(stat.S_IRUSR | stat.S_IWUSR)
    settings=Settings(project_root=tmp_path,runs_root=tmp_path/"runs",workspace_root=tmp_path/"workspace",
                      home_dir=tmp_path/"home",codex_home_dir=codex_home,local_input_dir=input_dir,
                      google_credentials_file=None)
    settings.workspace_dir.mkdir(); settings.runs_dir.mkdir()
    class Provider:
        def __init__(self,**_kwargs): pass
        def generate(self,**_kwargs):
            return SimpleNamespace(data={"document_read":True,"input_writable":False,"network_available":False},
                                   execution={"exit_code":0})
    monkeypatch.setattr(worker,"CodexProvider",Provider)
    monkeypatch.setattr(worker, "run_runtime_preflight", lambda _settings: {"status":"ok"})
    result=worker.run_container_preflight(settings)
    assert result["status"]=="ok"
    assert result["container"]=={"workspace_writable":True,"runs_writable":True,
                                 "codex_auth_accessible":True,"google_credentials_visible":False}
    assert result["codex"]["input_writable"] is False

def test_runtime_preflight_rejects_root_or_capabilities(tmp_path, monkeypatch):
    settings=Settings(project_root=tmp_path, runs_root=tmp_path/"runs", workspace_root=tmp_path/"workspace",
                      home_dir=tmp_path/"home", local_input_dir=tmp_path/"input", local_output_dir=tmp_path/"output", codex_home_dir=tmp_path/"codex")
    for path in (settings.runs_dir, settings.workspace_dir, settings.local_input_dir, settings.local_output_dir, settings.codex_home_dir): path.mkdir()
    (settings.codex_home_dir/"auth.json").write_text("{}"); (settings.codex_home_dir/"auth.json").chmod(0o600)
    monkeypatch.setattr(worker, "_runtime_diagnostics", lambda: {"uid":0,"process":{"CapEff":"0000000000000000","NoNewPrivs":"1"},"codex_version_exit_code":0})
    monkeypatch.setattr(worker, "_probe_writable", lambda path: path != settings.local_input_dir)
    with pytest.raises(RuntimeError, match="not_root"):
        worker.run_runtime_preflight(settings)

def test_runtime_preflight_initializes_missing_workspace(tmp_path, monkeypatch):
    input_dir=tmp_path/"input"; input_dir.mkdir()
    output_dir=tmp_path/"output"; output_dir.mkdir()
    codex_home=tmp_path/"codex"; codex_home.mkdir()
    auth=codex_home/"auth.json"; auth.write_text("{}"); auth.chmod(0o600)
    settings=Settings(project_root=tmp_path, runs_root=tmp_path/"runs", workspace_root=tmp_path/"missing-workspace",
                      home_dir=tmp_path/"missing-home", codex_home_dir=codex_home,
                      local_input_dir=input_dir, local_output_dir=output_dir)
    monkeypatch.setattr(worker, "_runtime_diagnostics", lambda: {"uid":10001, "gid":10001,
                        "process":{"CapEff":"0000000000000000", "NoNewPrivs":"1"}, "codex_version_exit_code":0})
    monkeypatch.setattr(worker, "_probe_writable", lambda path: path != input_dir)
    result=worker.run_runtime_preflight(settings)
    assert result["status"] == "ok"
    assert settings.workspace_dir.is_dir() and settings.home_dir.is_dir() and settings.runs_dir.is_dir()
