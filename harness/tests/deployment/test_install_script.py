"""Smoke tests for `install.sh`/`uninstall.sh`: never touches the real HOME,
`~/.codex`, `~/.claude` or any account; never invokes `claude` or `codex`.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess

import pytest

DEPLOYMENT = Path(__file__).parents[2] / "deployment"
INSTALL_SH = DEPLOYMENT / "install.sh"
UNINSTALL_SH = DEPLOYMENT / "uninstall.sh"
INSTALL_PS1 = DEPLOYMENT / "install.ps1"
UNINSTALL_PS1 = DEPLOYMENT / "uninstall.ps1"
REPO_ROOT = Path(__file__).parents[3]

NETWORK_MARKERS = (
    "Temporary failure in name resolution", "Name or service not known", "Could not resolve host",
    "Failed to download", "Download interrupted", "download was interrupted", "Could not connect to",
    "Failed to connect to", "Connection refused", "Connection reset", "Network is unreachable",
)

pytestmark = pytest.mark.skipif(platform.system() == "Windows", reason="install.sh is POSIX-specific")


def _skip_if_network_error(result: subprocess.CompletedProcess) -> None:
    text = (result.stdout + result.stderr).lower()
    if any(marker.lower() in text for marker in NETWORK_MARKERS):
        pytest.skip(f"red no disponible: {(result.stdout + result.stderr)[-400:]}")


def _run(command, *, env, cwd=None, timeout=300):
    return subprocess.run(command, env=env, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def test_without_git_stops_with_the_official_link(tmp_path: Path):
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    home = tmp_path / "home"
    env = {"PATH": str(empty_bin), "HOME": str(home), "LITMAN_APP": "codex"}
    result = _run(["/bin/sh", str(INSTALL_SH)], env=env)
    assert result.returncode != 0
    assert "git-scm.com" in result.stdout + result.stderr
    assert not home.exists()


def test_without_uv_stops_with_the_official_command(tmp_path: Path):
    git_bin = tmp_path / "git-bin"
    git_bin.mkdir()
    real_git = shutil.which("git")
    assert real_git
    (git_bin / "git").symlink_to(real_git)
    home = tmp_path / "home"
    env = {"PATH": str(git_bin), "HOME": str(home), "LITMAN_APP": "codex"}
    result = _run(["/bin/sh", str(INSTALL_SH)], env=env)
    assert result.returncode != 0
    assert "astral.sh/uv/install.sh" in result.stdout + result.stderr
    assert not home.exists()


def test_without_litman_app_stops_with_a_clear_message(tmp_path: Path):
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path / "home")}
    result = _run(["/bin/sh", str(INSTALL_SH)], env=env)
    assert result.returncode != 0
    assert "LITMAN_APP" in result.stdout + result.stderr


@pytest.fixture
def committed_repo_copy(tmp_path: Path) -> Path:
    """A git repo with one commit of the current working tree (tests the actual code)."""
    bare_source = tmp_path / "repo-source"
    bare_source.mkdir()
    files = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=REPO_ROOT, capture_output=True,
                           text=True, check=True).stdout.splitlines()
    for rel in files:
        src = REPO_ROOT / rel
        if not src.is_file():
            continue
        dest = bare_source / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    subprocess.run(["git", "init", "--quiet"], cwd=bare_source, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=bare_source, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=bare_source, check=True)
    subprocess.run(["git", "add", "-A"], cwd=bare_source, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "snapshot"], cwd=bare_source, check=True)
    subprocess.run(["git", "tag", "v0.1.0"], cwd=bare_source, check=True)
    return bare_source


def test_install_sh_end_to_end_then_idempotent_then_uninstall(tmp_path: Path, committed_repo_copy: Path):
    home = tmp_path / "home"
    home.mkdir()
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    (fake_bin / "codex").write_text("#!/bin/sh\nexit 0\n")
    (fake_bin / "codex").chmod(0o755)

    uv_path = shutil.which("uv")
    assert uv_path
    uv_dir = Path(uv_path).parent
    real_python_install_dir = subprocess.run(["uv", "python", "dir"], capture_output=True, text=True,
                                             check=True).stdout.strip()

    env = {
        "HOME": str(home),
        "PATH": f"{fake_bin}:{uv_dir}:/usr/bin:/bin",
        "LITMAN_APP": "codex",
        "LITMAN_REPO": str(committed_repo_copy),
        "LITMAN_SRC_DIR": str(home / "src"),
        "UV_CACHE_DIR": "/tmp/licitaBot-uv-cache",
        "UV_TOOL_DIR": str(tmp_path / "uv-tools"),
        "UV_TOOL_BIN_DIR": str(tmp_path / "uv-bin"),
        "UV_PYTHON_INSTALL_DIR": real_python_install_dir,
    }

    result = _run(["/bin/sh", str(INSTALL_SH)], env=env, timeout=600)
    _skip_if_network_error(result)
    assert result.returncode == 0, result.stdout + result.stderr

    litman_bin = Path(env["UV_TOOL_BIN_DIR"]) / "litman"
    assert litman_bin.is_file()
    diagnose = subprocess.run([str(litman_bin), "diagnose"], env={**os.environ, **env}, capture_output=True,
                              text=True, check=True)
    payload = json.loads(diagnose.stdout)
    assert payload["ok"] is True
    report = payload["result"]
    assert report["core_executable_found"] is True
    assert report["core"]["compatible"] is True
    assert report["installation"]["installed"] is True

    codex_config = home / ".codex" / "config.toml"
    config_text = codex_config.read_text(encoding="utf-8")
    assert config_text.count("# >>> litman") == 1

    # Idempotent re-run: a single MCP block, no failure.
    second = _run(["/bin/sh", str(INSTALL_SH)], env=env, timeout=600)
    _skip_if_network_error(second)
    assert second.returncode == 0, second.stdout + second.stderr
    assert codex_config.read_text(encoding="utf-8").count("# >>> litman") == 1

    uninstall_result = _run(["/bin/sh", str(UNINSTALL_SH)], env=env, timeout=300)
    assert uninstall_result.returncode == 0, uninstall_result.stdout + uninstall_result.stderr
    assert "# >>> litman" not in codex_config.read_text(encoding="utf-8")
    assert not (home / ".agents" / "skills" / "preparar-equipo").exists()
    assert not (home / ".codex" / "agents" / "lector-licitacion.toml").exists()
    assert (home / "LitMan").exists()  # workspace is only removed with --remove-workspace


def test_install_and_uninstall_ps1_contain_the_official_links_and_no_elevation():
    install_text = INSTALL_PS1.read_text(encoding="utf-8")
    uninstall_text = UNINSTALL_PS1.read_text(encoding="utf-8")
    assert "git-scm.com/downloads/win" in install_text
    assert "astral.sh/uv/install.ps1" in install_text
    assert "LITMAN_APP" in install_text
    assert "origin/HEAD" not in install_text and "origin/HEAD" not in INSTALL_SH.read_text(encoding="utf-8")
    assert "ErrorActionPreference" in install_text and "ErrorActionPreference" in uninstall_text
    for text in (install_text, uninstall_text):
        for forbidden in ("winget", "choco", "-Verb RunAs", "Start-Process"):
            assert forbidden not in text

    try:
        import subprocess as _subprocess
        pwsh = shutil.which("pwsh")
    except Exception:  # noqa: BLE001
        pwsh = None
    if pwsh is None:
        pytest.skip("pwsh no disponible: sólo validación estática")
    for script in (INSTALL_PS1, UNINSTALL_PS1):
        parse = _subprocess.run(
            [pwsh, "-NoProfile", "-Command",
             f"[System.Management.Automation.Language.Parser]::ParseFile('{script}', [ref]$null, [ref]$null)"],
            capture_output=True, text=True)
        assert parse.returncode == 0, parse.stderr


def test_install_sh_requires_a_stable_version_tag_before_installing(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "README").write_text("x")
    subprocess.run(["git", "add", "README"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "snapshot"], cwd=repo, check=True)
    subprocess.run(["git", "tag", "v0.9.0"], cwd=repo, check=True)
    subprocess.run(["git", "tag", "v0.10.0"], cwd=repo, check=True)
    subprocess.run(["git", "tag", "v1.0.0-rc1"], cwd=repo, check=True)
    subprocess.run(["git", "tag", "vfoo"], cwd=repo, check=True)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    codex = fake_bin / "codex"
    codex.write_text("#!/bin/sh\nexit 0\n")
    codex.chmod(0o755)
    log = tmp_path / "calls"
    fake_uv = fake_bin / "uv"
    fake_uv.write_text("#!/bin/sh\nif [ \"$1\" = tool ] && [ \"$2\" = dir ]; then echo \"$UV_BIN\"; exit 0; fi\necho called >> \"$CALL_LOG\"\nexit 0\n")
    fake_uv.chmod(0o755)
    uv_bin = tmp_path / "uv-bin"
    uv_bin.mkdir()
    (uv_bin / "litman").write_text("#!/bin/sh\nexit 0\n")
    (uv_bin / "litman").chmod(0o755)
    env = {"PATH": f"{fake_bin}:/usr/bin:/bin", "HOME": str(tmp_path / "home"), "LITMAN_APP": "codex",
           "LITMAN_REPO": str(repo), "LITMAN_SRC_DIR": str(repo), "CALL_LOG": str(log), "UV_BIN": str(uv_bin)}
    result = _run(["/bin/sh", str(INSTALL_SH)], env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "v0.10.0" in subprocess.run(["git", "-C", str(repo), "describe", "--tags", "--exact-match"],
                                        capture_output=True, text=True, check=True).stdout
    assert log.is_file()


def test_install_sh_stops_without_a_stable_version_tag(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "README").write_text("x")
    subprocess.run(["git", "add", "README"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "snapshot"], cwd=repo, check=True)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("codex", "uv"):
        path = fake_bin / name
        path.write_text("#!/bin/sh\necho called >> \"$CALL_LOG\"\nexit 0\n")
        path.chmod(0o755)
    log = tmp_path / "calls"
    env = {"PATH": f"{fake_bin}:/usr/bin:/bin", "HOME": str(tmp_path / "home"), "LITMAN_APP": "codex",
           "LITMAN_REPO": str(repo), "LITMAN_SRC_DIR": str(repo), "CALL_LOG": str(log)}
    result = _run(["/bin/sh", str(INSTALL_SH)], env=env)
    assert result.returncode != 0
    assert "No existe una versión publicada" in result.stdout + result.stderr
    assert not log.exists()


def test_without_provider_cli_stops_before_cloning_or_installing(tmp_path: Path):
    git_bin = tmp_path / "git-bin"
    git_bin.mkdir()
    real_git = shutil.which("git")
    assert real_git
    (git_bin / "git").symlink_to(real_git)

    uv_log = tmp_path / "uv-calls.log"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    uv_script = fake_bin / "uv"
    uv_script.write_text(f'#!/bin/sh\necho "$@" >> "{uv_log}"\nexit 0\n')
    uv_script.chmod(0o755)

    home = tmp_path / "home"
    src = tmp_path / "src"
    env = {"PATH": f"{git_bin}:{fake_bin}", "HOME": str(home), "LITMAN_APP": "codex",
           "LITMAN_SRC_DIR": str(src)}
    result = _run(["/bin/sh", str(INSTALL_SH)], env=env)
    assert result.returncode != 0
    assert "github.com/openai/codex" in result.stdout + result.stderr
    assert not src.exists()
    assert not uv_log.exists()


def test_install_ps1_checks_provider_cli_before_clone_and_tool_install():
    text = INSTALL_PS1.read_text(encoding="utf-8")
    codex_check = text.index("Get-Command codex")
    claude_check = text.index("Get-Command claude")
    clone_idx = text.index("git clone")
    tool_install_idx = text.index("uv tool install")
    assert codex_check < clone_idx and claude_check < clone_idx
    assert codex_check < tool_install_idx and claude_check < tool_install_idx


def test_uninstall_sh_stops_before_uv_tool_uninstall_when_litman_uninstall_fails(tmp_path: Path):
    bin_dir = tmp_path / "uv-bin"
    bin_dir.mkdir()
    litman_bin = bin_dir / "litman"
    litman_bin.write_text("#!/bin/sh\nexit 2\n")
    litman_bin.chmod(0o755)

    uv_log = tmp_path / "uv-calls.log"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    uv_script = fake_bin / "uv"
    uv_script.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{uv_log}"\n'
        'if [ "$1" = "tool" ] && [ "$2" = "dir" ]; then\n'
        f'  echo "{bin_dir}"\n'
        "  exit 0\n"
        "fi\n"
        "exit 0\n"
    )
    uv_script.chmod(0o755)

    src = tmp_path / "src"
    src.mkdir()
    (src / "marker.txt").write_text("keep")

    env = {"PATH": str(fake_bin), "HOME": str(tmp_path / "home"), "LITMAN_SRC_DIR": str(src)}
    result = _run(["/bin/sh", str(UNINSTALL_SH)], env=env)
    assert result.returncode != 0
    assert src.exists()
    assert "uninstall" not in (uv_log.read_text() if uv_log.exists() else "")


def test_uninstall_ps1_checks_lastexitcode_after_litman_uninstall():
    text = UNINSTALL_PS1.read_text(encoding="utf-8")
    call_idx = text.index("& $Python -m litman_harness.interfaces.cli uninstall")
    check_idx = text.index("$LASTEXITCODE -ne 0", call_idx)
    tool_uninstall_idx = text.index("uv tool uninstall", call_idx)
    assert call_idx < check_idx < tool_uninstall_idx


def test_ps1_scripts_run_the_cli_through_the_tool_python_not_the_litman_launcher():
    install_text = INSTALL_PS1.read_text(encoding="utf-8")
    uninstall_text = UNINSTALL_PS1.read_text(encoding="utf-8")
    for text in (install_text, uninstall_text):
        assert "litman.exe" not in text
        assert "uv tool dir --bin" not in text
        assert "$ToolDir = uv tool dir" in text
        assert "$Python = Join-Path $ToolDir 'litman-harness\\Scripts\\python.exe'" in text
    assert "& $Python -m litman_harness.interfaces.cli install --app $env:LITMAN_APP --source $Src" in install_text
    assert "& $Python -m litman_harness.interfaces.cli uninstall @UninstallArgs" in uninstall_text


def test_ps1_scripts_capture_the_uv_tool_dir_as_utf8_and_restore_the_encoding():
    for script in (INSTALL_PS1, UNINSTALL_PS1):
        text = script.read_text(encoding="utf-8")
        save_idx = text.index("$PreviousEncoding = [Console]::OutputEncoding")
        set_idx = text.index("[Console]::OutputEncoding = [System.Text.Encoding]::UTF8")
        capture = re.search(r"try \{\s*\$ToolDir = uv tool dir\s*\} finally \{([^}]*)\}", text)
        assert capture, script.name
        assert save_idx < set_idx < capture.start()
        assert "[Console]::OutputEncoding = $PreviousEncoding" in capture.group(1)


def test_install_ps1_checks_the_tool_python_exists_before_running_it():
    text = INSTALL_PS1.read_text(encoding="utf-8")
    check_idx = text.index("if (-not (Test-Path $Python)) {")
    call_idx = text.index("& $Python")
    assert check_idx < call_idx
    failure_branch = text[check_idx:text.index("}", check_idx)]
    assert re.search(r'Write-Error "No se encuentra[^"]*\$Python', failure_branch)
    assert "exit 1" in failure_branch


def test_uninstall_ps1_skips_the_cli_uninstall_when_the_tool_python_is_absent():
    text = UNINSTALL_PS1.read_text(encoding="utf-8")
    guard_idx = text.index("if (Test-Path $Python) {")
    call_idx = text.index("& $Python -m litman_harness.interfaces.cli uninstall")
    tool_uninstall_idx = text.index("uv tool uninstall litman-harness")
    assert guard_idx < call_idx < tool_uninstall_idx
