import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from litman_core import cli


def _config(path: Path) -> None:
    path.write_text("[job]\nid='run-id'\ntype='assessment'\n[input]\nkind='local'\nlocation='case'\n[output]\ndirectory='out'\n", encoding="utf-8")


def test_cli_run_loads_default_config_and_emits_current_result(tmp_path, monkeypatch, capsys):
    _config(tmp_path / "config.toml"); (tmp_path / "case").mkdir(); monkeypatch.chdir(tmp_path)
    seen = []
    class Runner:
        def __init__(self, settings): pass
        def run(self, request):
            seen.append(request)
            return SimpleNamespace(job_id=request.job_id, publication_id="run-id-20261008T153045.123456Z", status="succeeded", local_path=Path("/run"), artifacts=(), remote=None)
    monkeypatch.setattr(cli, "JobRunner", Runner)
    cli.main(["run"])
    payload = json.loads(capsys.readouterr().out)
    assert seen[0].job_id == "run-id"
    assert payload["publication_id"].startswith("run-id-") and payload["local_path"] == "/run"


def test_cli_loads_adjacent_env_without_overwriting_inherited_value(tmp_path, monkeypatch, capsys):
    config = tmp_path / "config.toml"; _config(config); (tmp_path / "case").mkdir()
    (tmp_path / ".env").write_text("TEST_CLI_ENV=from-file\n", encoding="utf-8")
    monkeypatch.setenv("TEST_CLI_ENV", "inherited")
    class Runner:
        def __init__(self, settings): pass
        def run(self, request): return SimpleNamespace(job_id=request.job_id, publication_id="id", status="succeeded", local_path=Path("/run"), artifacts=(), remote=None)
    monkeypatch.setattr(cli, "JobRunner", Runner)
    cli.main(["run", "--config", str(config)])
    assert __import__("os").environ["TEST_CLI_ENV"] == "inherited"
    capsys.readouterr()


@pytest.mark.parametrize("command", ["assess", "analyze", "check"])
def test_removed_commands_are_rejected(command):
    with pytest.raises(SystemExit) as error:
        cli.main([command])
    assert error.value.code == 2
