from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sysconfig
import tomllib

import pytest

from litman_harness.errors import HarnessError
from litman_harness import installation
from litman_harness.adapters.core import script_path

REPO = Path(__file__).parents[2]


def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **extra: str) -> dict[str, str]:
    values = {"XDG_STATE_HOME": str(tmp_path / "state"), "XDG_CONFIG_HOME": str(tmp_path / "config"),
              "CODEX_HOME": str(tmp_path / "home" / ".codex"), **extra}
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


def _patch_scripts(monkeypatch: pytest.MonkeyPatch, scripts_dir: Path) -> None:
    scripts_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(installation, "script_path", lambda name: scripts_dir / name)


class FakeClaudeRun:
    """Records calls; ``litman`` is never registered unless ``add`` succeeded."""

    def __init__(self, *, foreign: bool = False):
        self.calls: list[list[str]] = []
        self.registered = foreign

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        sub = command[2] if len(command) > 2 else None
        if sub == "get":
            return subprocess.CompletedProcess(command, 0 if self.registered else 1, "", "")
        if sub == "remove":
            self.registered = False
            return subprocess.CompletedProcess(command, 0, "", "")
        if sub == "add":
            self.registered = True
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(f"unexpected claude call: {command}")


def test_install_codex_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = _env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    _patch_scripts(monkeypatch, tmp_path / "scripts")

    result = installation.install(app="codex", source=REPO, home=home, env=env)
    assert result["app"] == "codex"
    assert set(result["installed"]) >= {"workspace", "skills", "subagent", "mcp"}

    agents_md = (home / "LitMan" / "AGENTS.md").read_text(encoding="utf-8")
    assert str(tmp_path / "scripts" / "litman") in agents_md
    for name in installation.SKILL_NAMES:
        assert (home / ".agents" / "skills" / name / "SKILL.md").is_file()
    assert (env["CODEX_HOME"] and (Path(env["CODEX_HOME"]) / "agents" / "lector-licitacion.toml").is_file())

    config_text = (Path(env["CODEX_HOME"]) / "config.toml").read_text(encoding="utf-8")
    parsed = tomllib.loads(config_text)
    assert parsed["mcp_servers"]["litman"]["tool_timeout_sec"] == 7200
    assert parsed["mcp_servers"]["litman"]["command"] == str(tmp_path / "scripts" / "litman-mcp")
    assert installation.manifest_path(env).is_file()
    manifest = json.loads(installation.manifest_path(env).read_text(encoding="utf-8"))
    assert manifest["source"] == str(REPO.resolve())


def test_install_is_idempotent_and_updates_a_changed_skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = _env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    _patch_scripts(monkeypatch, tmp_path / "scripts")

    installation.install(app="codex", source=REPO, home=home, env=env)
    installation.install(app="codex", source=REPO, home=home, env=env)

    config_text = (Path(env["CODEX_HOME"]) / "config.toml").read_text(encoding="utf-8")
    assert config_text.count(installation.CODEX_BLOCK_START) == 1

    skill_dir = home / ".agents" / "skills" / "preparar-equipo"
    (skill_dir / "SKILL.md").write_text("modificado", encoding="utf-8")
    installation.install(app="codex", source=REPO, home=home, env=env)
    assert (skill_dir / "SKILL.md").read_text(encoding="utf-8") != "modificado"


@pytest.mark.parametrize("app", installation.APPS)
def test_install_copies_current_conectar_licitacion_skill_for_each_app(
    app: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    env = _env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    _patch_scripts(monkeypatch, tmp_path / "scripts")
    if app == "claude":
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "claude").write_text("#!/bin/sh\n")
        (bin_dir / "claude").chmod(0o755)
        monkeypatch.setenv("PATH", str(bin_dir))

    installation.install(app=app, source=REPO, home=home, env=env, run=FakeClaudeRun())

    skill_root = home / (".claude/skills" if app == "claude" else ".agents/skills")
    installed = skill_root / "conectar-licitacion" / "SKILL.md"
    source = REPO / "harness/agent/skills/conectar-licitacion/SKILL.md"
    assert installed.read_bytes() == source.read_bytes()


def test_config_toml_with_foreign_content_is_preserved_and_windows_path_reread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    env = _env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    _patch_scripts(monkeypatch, tmp_path / "scripts")
    codex_home = Path(env["CODEX_HOME"])
    codex_home.mkdir(parents=True)
    original = '# comentario propio\n[profiles.default]\nmodel = "gpt-5"\n'
    (codex_home / "config.toml").write_text(original, encoding="utf-8")

    installation.install(app="codex", source=REPO, home=home, env=env)
    text = (codex_home / "config.toml").read_text(encoding="utf-8")
    assert original.strip() in text
    parsed = tomllib.loads(text)
    assert parsed["profiles"]["default"]["model"] == "gpt-5"

    # A Windows-style path survives a round trip through json.dumps escaping.
    def windows_scripts(name: str) -> Path:
        return Path(r"C:\Users\x\litman-mcp.exe") if name == "litman-mcp" else tmp_path / "scripts" / name
    monkeypatch.setattr(installation, "script_path", windows_scripts)
    installation.install(app="codex", source=REPO, home=home, env=env)
    reread = tomllib.loads((codex_home / "config.toml").read_text(encoding="utf-8"))
    assert reread["mcp_servers"]["litman"]["command"] == r"C:\Users\x\litman-mcp.exe"


def test_foreign_mcp_server_in_config_toml_is_a_conflict_and_file_is_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    env = _env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    _patch_scripts(monkeypatch, tmp_path / "scripts")
    codex_home = Path(env["CODEX_HOME"])
    codex_home.mkdir(parents=True)
    original = '[mcp_servers.litman]\ncommand = "/usr/bin/otra-cosa"\n'
    (codex_home / "config.toml").write_text(original, encoding="utf-8")

    with pytest.raises(HarnessError) as raised:
        installation.install(app="codex", source=REPO, home=home, env=env)
    assert raised.value.code == "install_conflict"
    assert (codex_home / "config.toml").read_text(encoding="utf-8") == original
    assert not installation.manifest_path(env).is_file()


def test_invalid_toml_is_reported_without_touching_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = _env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    _patch_scripts(monkeypatch, tmp_path / "scripts")
    codex_home = Path(env["CODEX_HOME"])
    codex_home.mkdir(parents=True)
    original = "not valid toml ="
    (codex_home / "config.toml").write_text(original, encoding="utf-8")

    with pytest.raises(HarnessError) as raised:
        installation.install(app="codex", source=REPO, home=home, env=env)
    assert raised.value.code == "invalid_codex_config"
    assert (codex_home / "config.toml").read_text(encoding="utf-8") == original


def test_foreign_skill_folder_is_a_conflict_and_nothing_is_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = _env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    _patch_scripts(monkeypatch, tmp_path / "scripts")
    foreign = home / ".agents" / "skills" / "conectar-licitacion"
    foreign.mkdir(parents=True)
    (foreign / "mío.md").write_text("ajeno", encoding="utf-8")

    with pytest.raises(HarnessError) as raised:
        installation.install(app="codex", source=REPO, home=home, env=env)
    assert raised.value.code == "install_conflict"
    assert (foreign / "mío.md").is_file()
    assert not installation.manifest_path(env).is_file()


def test_claude_install_registers_mcp_and_reinstall_removes_and_adds_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    env = _env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    _patch_scripts(monkeypatch, tmp_path / "scripts")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "claude").write_text("#!/bin/sh\n")
    (bin_dir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))

    fake_run = FakeClaudeRun()
    result = installation.install(app="claude", source=REPO, home=home, env=env, run=fake_run)
    assert "mcp" in result["installed"]
    add_calls = [c for c in fake_run.calls if c[2] == "add"]
    assert len(add_calls) == 1 and add_calls[0][-1] == str(tmp_path / "scripts" / "litman-mcp")
    settings = json.loads((home / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert settings["env"]["MCP_TOOL_TIMEOUT"] == "7200000"

    fake_run.calls.clear()
    installation.install(app="claude", source=REPO, home=home, env=env, run=fake_run)
    kinds = [c[2] for c in fake_run.calls]
    assert "remove" in kinds and "add" in kinds


@pytest.mark.parametrize("app", installation.APPS)
def test_help_skill_is_installed_recorded_and_uninstalled(app: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = _env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    _patch_scripts(monkeypatch, tmp_path / "scripts")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "claude").write_text("#!/bin/sh\n")
    (bin_dir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))

    installation.install(app=app, source=REPO, home=home, env=env, run=FakeClaudeRun())
    skill = (home / ".claude" / "skills" if app == "claude" else home / ".agents" / "skills") / "ayuda-litman"
    assert (skill / "SKILL.md").is_file()
    update_skill = skill.parent / "actualizar-equipo"
    assert (update_skill / "SKILL.md").is_file()
    manifest = json.loads(installation.manifest_path(env).read_text(encoding="utf-8"))
    assert "ayuda-litman" in manifest["skills"]
    assert "actualizar-equipo" in manifest["skills"]

    result = installation.uninstall(home=home, env=env, run=FakeClaudeRun(foreign=True))
    assert "skill:ayuda-litman" in result["removed"]
    assert not skill.exists()
    assert "skill:actualizar-equipo" in result["removed"]
    assert not update_skill.exists()



def test_claude_install_creates_claude_md_with_agents_reference(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = _env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    _patch_scripts(monkeypatch, tmp_path / "scripts")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "claude").write_text("#!/bin/sh\n")
    (bin_dir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))

    result = installation.install(app="claude", source=REPO, home=home, env=env, run=FakeClaudeRun())
    assert "claude_md" in result["installed"]
    claude_md = home / "LitMan" / "CLAUDE.md"
    assert claude_md.read_text(encoding="utf-8") == "@AGENTS.md\n"
    manifest = json.loads(installation.manifest_path(env).read_text(encoding="utf-8"))
    assert manifest["claude_md_created"] is True

    # idempotent: re-running install does not duplicate or corrupt the file
    result = installation.install(app="claude", source=REPO, home=home, env=env, run=FakeClaudeRun())
    assert claude_md.read_text(encoding="utf-8") == "@AGENTS.md\n"


def test_codex_install_does_not_create_claude_md(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = _env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    _patch_scripts(monkeypatch, tmp_path / "scripts")

    result = installation.install(app="codex", source=REPO, home=home, env=env)
    assert "claude_md" not in result["installed"]
    assert not (home / "LitMan" / "CLAUDE.md").exists()
    manifest = json.loads(installation.manifest_path(env).read_text(encoding="utf-8"))
    assert "claude_md_created" not in manifest


def test_claude_uninstall_keeps_claude_md_without_remove_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    env = _env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    _patch_scripts(monkeypatch, tmp_path / "scripts")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "claude").write_text("#!/bin/sh\n")
    (bin_dir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    installation.install(app="claude", source=REPO, home=home, env=env, run=FakeClaudeRun())
    claude_md = home / "LitMan" / "CLAUDE.md"
    assert claude_md.is_file()

    result = installation.uninstall(home=home, env=env, run=FakeClaudeRun())
    assert "claude_md" in result["kept"]
    assert claude_md.is_file()


def test_claude_uninstall_removes_claude_md_with_remove_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    env = _env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    _patch_scripts(monkeypatch, tmp_path / "scripts")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "claude").write_text("#!/bin/sh\n")
    (bin_dir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    installation.install(app="claude", source=REPO, home=home, env=env, run=FakeClaudeRun())
    claude_md = home / "LitMan" / "CLAUDE.md"
    assert claude_md.is_file()

    result = installation.uninstall(home=home, env=env, remove_workspace=True, run=FakeClaudeRun())
    assert "claude_md" in result["removed"]
    assert not claude_md.exists()


def test_claude_foreign_mcp_server_is_a_conflict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = _env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    _patch_scripts(monkeypatch, tmp_path / "scripts")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "claude").write_text("#!/bin/sh\n")
    (bin_dir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))

    fake_run = FakeClaudeRun(foreign=True)
    with pytest.raises(HarnessError) as raised:
        installation.install(app="claude", source=REPO, home=home, env=env, run=fake_run)
    assert raised.value.code == "install_conflict"
    assert not installation.manifest_path(env).is_file()


def test_claude_cli_missing_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = _env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    _patch_scripts(monkeypatch, tmp_path / "scripts")
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))

    with pytest.raises(HarnessError) as raised:
        installation.install(app="claude", source=REPO, home=home, env=env, run=FakeClaudeRun())
    assert raised.value.code == "claude_cli_missing"


def test_claude_settings_with_own_timeout_env_is_not_overwritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = _env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    _patch_scripts(monkeypatch, tmp_path / "scripts")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "claude").write_text("#!/bin/sh\n")
    (bin_dir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / "settings.json").write_text(json.dumps({"env": {"MCP_TOOL_TIMEOUT": "1000"}}), encoding="utf-8")

    result = installation.install(app="claude", source=REPO, home=home, env=env, run=FakeClaudeRun())
    assert "claude_timeout_env" not in result["installed"]
    settings = json.loads((claude_dir / "settings.json").read_text(encoding="utf-8"))
    assert settings["env"]["MCP_TOOL_TIMEOUT"] == "1000"


def test_uninstall_removes_only_the_manifest_and_keeps_user_additions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = _env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    _patch_scripts(monkeypatch, tmp_path / "scripts")
    installation.install(app="codex", source=REPO, home=home, env=env)

    extra_skill = home / ".agents" / "skills" / "otra"
    extra_skill.mkdir(parents=True)
    (extra_skill / "SKILL.md").write_text("ajena", encoding="utf-8")
    (home / "LitMan" / "mis-notas.txt").write_text("mío", encoding="utf-8")

    result = installation.uninstall(home=home, env=env)
    assert any(r.startswith("skill:") for r in result["removed"])
    assert "mcp" in result["removed"]
    for name in installation.SKILL_NAMES:
        assert not (home / ".agents" / "skills" / name).exists()
    assert extra_skill.is_dir()
    assert (home / "LitMan").is_dir() and (home / "LitMan" / "mis-notas.txt").is_file()
    assert "workspace" in result["kept"]
    codex_config = (Path(env["CODEX_HOME"]) / "config.toml").read_text(encoding="utf-8")
    assert installation.CODEX_BLOCK_START not in codex_config
    assert not installation.manifest_path(env).is_file()


def test_uninstall_with_remove_workspace_and_purge_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = _env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    _patch_scripts(monkeypatch, tmp_path / "scripts")
    installation.install(app="codex", source=REPO, home=home, env=env)
    client_file = tmp_path / "client_secret.json"
    client_file.write_text(json.dumps({"installed": {"client_id": "a", "client_secret": "b",
                                                      "auth_uri": "https://x", "token_uri": "https://y"}}))
    installation.import_oauth_client(client_file, env=env)

    result = installation.uninstall(home=home, env=env, remove_workspace=True, purge_data=True)
    assert "workspace" in result["removed"]
    assert not (home / "LitMan").exists()
    assert "oauth_client" in result["removed"]
    from litman_harness.local_paths import client_path
    assert not client_path(env).exists()


def test_uninstall_without_manifest_is_a_noop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = _env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    result = installation.uninstall(home=home, env=env)
    assert result == {"removed": [], "kept": [], "failed": []}


def test_uninstall_reports_failed_folder_and_file_and_keeps_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    env = _env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    _patch_scripts(monkeypatch, tmp_path / "scripts")
    installation.install(app="codex", source=REPO, home=home, env=env)

    from litman_harness.local_paths import token_path
    token_file = token_path(env)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text("{}", encoding="utf-8")

    real_remove = installation._remove
    failing_skill = installation.SKILL_NAMES[0]

    def fake_remove(path: Path, *, is_dir: bool) -> bool:
        if is_dir and path.name == failing_skill:
            return False
        if not is_dir and path.name == "token.json":
            return False
        return real_remove(path, is_dir=is_dir)

    monkeypatch.setattr(installation, "_remove", fake_remove)

    result = installation.uninstall(home=home, env=env, purge_data=True)
    assert f"skill:{failing_skill}" in result["failed"]
    assert "token" in result["failed"]
    for name in installation.SKILL_NAMES:
        if name != failing_skill:
            assert f"skill:{name}" in result["removed"]
    assert installation.manifest_path(env).is_file()

    monkeypatch.setattr(installation, "_remove", real_remove)
    retry = installation.uninstall(home=home, env=env, purge_data=True)
    assert retry["failed"] == []
    assert f"skill:{failing_skill}" in retry["removed"]
    assert "token" in retry["removed"]
    assert not installation.manifest_path(env).is_file()


def test_import_oauth_client_copies_with_private_permissions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = _env(tmp_path, monkeypatch)
    content = {"installed": {"client_id": "a", "client_secret": "b", "auth_uri": "https://x",
                              "token_uri": "https://y"}}
    source = tmp_path / "client_secret.json"
    source.write_text(json.dumps(content), encoding="utf-8")

    result = installation.import_oauth_client(source, env=env)
    assert result == {"ok": True, "imported": True}
    from litman_harness.local_paths import client_path
    dest = client_path(env)
    assert json.loads(dest.read_text(encoding="utf-8")) == content
    assert dest.stat().st_mode & 0o777 == 0o600
    assert dest.parent.stat().st_mode & 0o777 == 0o700
    assert source.is_file()


def test_import_oauth_client_with_delete_original(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = _env(tmp_path, monkeypatch)
    content = {"installed": {"client_id": "a", "client_secret": "b", "auth_uri": "https://x",
                              "token_uri": "https://y"}}
    source = tmp_path / "client_secret.json"
    source.write_text(json.dumps(content), encoding="utf-8")
    installation.import_oauth_client(source, delete_original=True, env=env)
    assert not source.exists()


@pytest.mark.parametrize("content,expected_message_absent", [
    (json.dumps({"web": {"client_id": "secreto-id", "client_secret": "secreto-value",
                         "auth_uri": "x", "token_uri": "y"}}), "secreto-value"),
    ("not json", "not json"),
    (json.dumps({"installed": {"client_id": "secreto-id"}}), "secreto-id"),
])
def test_import_oauth_client_rejects_invalid_clients_without_leaking_the_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content, expected_message_absent,
):
    env = _env(tmp_path, monkeypatch)
    source = tmp_path / "client_secret.json"
    source.write_text(content, encoding="utf-8")
    with pytest.raises(HarnessError) as raised:
        installation.import_oauth_client(source, env=env)
    assert raised.value.code == "invalid_oauth_client"
    assert expected_message_absent not in str(raised.value)


def test_import_oauth_client_rejects_oversized_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = _env(tmp_path, monkeypatch)
    source = tmp_path / "client_secret.json"
    source.write_text("x" * (installation.MAX_OAUTH_CLIENT_BYTES + 1), encoding="utf-8")
    with pytest.raises(HarnessError) as raised:
        installation.import_oauth_client(source, env=env)
    assert raised.value.code == "invalid_oauth_client"


def test_status_without_manifest_reports_not_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = _env(tmp_path, monkeypatch)
    assert installation.status(env=env) == {"installed": False}


def test_status_reports_installed_state_and_detects_removed_skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = _env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    _patch_scripts(monkeypatch, tmp_path / "scripts")
    installation.install(app="codex", source=REPO, home=home, env=env)

    report = installation.status(env=env, home=home)
    assert report == {"installed": True, "app": "codex", "workspace": True, "skills": True, "subagent": True,
                      "mcp_registered": True, "oauth_client_imported": False}

    shutil_rmtree_target = home / ".agents" / "skills" / "preparar-equipo"
    import shutil
    shutil.rmtree(shutil_rmtree_target)
    report = installation.status(env=env, home=home)
    assert report["skills"] is False
    assert str(tmp_path) not in repr(report)


def test_litman_command_on_windows_runs_the_cli_through_the_tool_python(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(installation.platform, "system", lambda: "Windows")
    python = Path(sysconfig.get_path("scripts")) / "python.exe"
    assert installation.litman_command() == f'& "{python}" -m litman_harness.interfaces.cli'


def test_litman_command_on_posix_is_the_litman_script(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(installation.platform, "system", lambda: "Linux")
    assert installation.litman_command() == str(script_path("litman"))


def test_install_on_windows_renders_the_python_m_litman_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = _env(tmp_path, monkeypatch)
    home = tmp_path / "home"
    monkeypatch.setattr(installation.platform, "system", lambda: "Windows")

    installation.install(app="codex", source=REPO, home=home, env=env)

    agents_md = (home / "LitMan" / "AGENTS.md").read_text(encoding="utf-8")
    python = Path(sysconfig.get_path("scripts")) / "python.exe"
    assert f'`& "{python}" -m litman_harness.interfaces.cli`' in agents_md
    assert "litman.exe" not in agents_md
    config = tomllib.loads((Path(env["CODEX_HOME"]) / "config.toml").read_text(encoding="utf-8"))
    assert config["mcp_servers"]["litman"]["command"] == str(Path(sysconfig.get_path("scripts")) / "litman-mcp.exe")
