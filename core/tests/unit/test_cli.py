import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from litman_core import __version__, cli
from litman_core.errors import CoreError


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
    assert payload["contract"] == 1
    assert payload["status"] == "succeeded"
    assert payload["publication_id"].startswith("run-id-") and payload["local_path"] == "/run"
    assert payload["artifacts"] == []


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


class _Artifact(SimpleNamespace):
    pass


def _artifact(role: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(role=role, name=name, uri=f"file:///run/{name}", checksum="0" * 64)


@pytest.mark.parametrize("job_type,artifacts", [
    ("assessment", [("opportunity_report", "ficha_oportunidad.pdf")]),
    ("detailed-analysis", [
        ("technical_summary", "resumen_tecnico.docx"),
        ("bid_preparation_guide", "guia_preparacion_oferta.docx"),
        ("technical_document", "memoria_tecnica.docx"),
        ("economic_simulator", "simulador_economico.xlsx"),
    ]),
])
def test_cli_run_succeeds_with_roled_artifacts_by_job_type(tmp_path, monkeypatch, capsys, job_type, artifacts):
    config = tmp_path / "config.toml"
    config.write_text(f"[job]\nid='run-id'\ntype='{job_type}'\n[input]\nkind='local'\nlocation='case'\n[output]\ndirectory='out'\n", encoding="utf-8")
    (tmp_path / "case").mkdir(); monkeypatch.chdir(tmp_path)
    produced = [_artifact(role, name) for role, name in artifacts]
    class Runner:
        def __init__(self, settings): pass
        def run(self, request):
            return SimpleNamespace(job_id=request.job_id, publication_id="run-id-x", status="succeeded", local_path=Path("/run"), artifacts=produced, remote=None)
    monkeypatch.setattr(cli, "JobRunner", Runner)
    cli.main(["run"])
    out, err = capsys.readouterr()
    assert err == ""
    payload = json.loads(out)
    assert payload["status"] == "succeeded"
    assert [item["role"] for item in payload["artifacts"]] == [role for role, _ in artifacts]


@pytest.mark.parametrize("code", [
    "invalid_input",
    "llm_unavailable",
    "analysis_failed",
    "publication_failed",
])
def test_cli_run_reports_each_core_error_code(tmp_path, monkeypatch, capsys, code):
    _config(tmp_path / "config.toml"); (tmp_path / "case").mkdir(); monkeypatch.chdir(tmp_path)
    class Runner:
        def __init__(self, settings): pass
        def run(self, request):
            raise CoreError(code, "mensaje de prueba", Path("/run"))
    monkeypatch.setattr(cli, "JobRunner", Runner)
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["run"])
    assert exc_info.value.code == 1
    out, err = capsys.readouterr()
    assert err == ""
    payload = json.loads(out)
    assert payload["contract"] == 1
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == code
    assert payload["error"]["message"] == "mensaje de prueba"
    assert payload["local_path"] == "/run"


def test_cli_run_reports_invalid_config_without_local_path(tmp_path, monkeypatch, capsys):
    config = tmp_path / "config.toml"
    config.write_text("[job]\ntype='assessment'\n[analysis]\n[input]\nlocation='case'\n[output]\ndirectory='out'\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["run", "--config", str(config)])
    assert exc_info.value.code == 1
    out, _ = capsys.readouterr()
    payload = json.loads(out)
    assert payload["error"]["code"] == "invalid_config"
    assert "local_path" not in payload


def test_cli_run_reports_internal_for_unexpected_exception(tmp_path, monkeypatch, capsys):
    _config(tmp_path / "config.toml"); (tmp_path / "case").mkdir(); monkeypatch.chdir(tmp_path)
    class Runner:
        def __init__(self, settings): pass
        def run(self, request):
            raise RuntimeError("explosión inesperada")
    monkeypatch.setattr(cli, "JobRunner", Runner)
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["run"])
    assert exc_info.value.code == 1
    out, _ = capsys.readouterr()
    payload = json.loads(out)
    assert payload["error"]["code"] == "internal"


def test_cli_run_missing_config_file_exits_with_invalid_config(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["run", "--config", str(tmp_path / "missing.toml")])
    assert exc_info.value.code == 1
    out, _ = capsys.readouterr()
    payload = json.loads(out)
    assert payload["error"]["code"] == "invalid_config"


def test_cli_argparse_misuse_exits_2_without_json(capsys):
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["not-a-command"])
    assert exc_info.value.code == 2
    out, err = capsys.readouterr()
    assert out == ""
    with pytest.raises(json.JSONDecodeError):
        json.loads(err)


def test_cli_info_emits_contract_version_and_providers(capsys):
    cli.main(["info"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["contract"] == 1
    assert payload["version"] == __version__
    assert payload["providers"] == ["claude-code", "codex"]
    assert "environment" in payload


@pytest.mark.parametrize("codex_cli,claude_cli,codex_session,claude_session,browser", [
    (True, True, True, True, True),
    (False, False, False, False, False),
])
def test_cli_info_environment_reports_presence(
    tmp_path, monkeypatch, capsys, codex_cli, claude_cli, codex_session, claude_session, browser,
):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    if codex_cli:
        (bin_dir / "codex").write_text("#!/bin/sh\n"); (bin_dir / "codex").chmod(0o755)
    if claude_cli:
        (bin_dir / "claude").write_text("#!/bin/sh\n"); (bin_dir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))

    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    if codex_session:
        (codex_home / "auth.json").write_text("{}")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    claude_config_dir = tmp_path / "claude_config"
    claude_config_dir.mkdir()
    if claude_session:
        (claude_config_dir / ".credentials.json").write_text("{}")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_config_dir))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    monkeypatch.setattr(
        "litman_core.generation.opportunity_report.generator._find_browser",
        lambda browser_name: "/usr/bin/google-chrome" if browser else None,
    )

    cli.main(["info"])
    payload = json.loads(capsys.readouterr().out)
    env = payload["environment"]
    assert env["providers"]["codex"] == {"cli": codex_cli, "session": codex_session}
    assert env["providers"]["claude-code"] == {"cli": claude_cli, "session": claude_session}
    assert env["pdf_browser"] == browser
