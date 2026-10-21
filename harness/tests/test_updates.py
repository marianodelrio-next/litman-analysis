from __future__ import annotations

import json
import shlex
import subprocess

import pytest

from litman_harness import updates
from litman_harness.errors import HarnessError


def test_check_update_returns_newer_tag_changes_and_posix_command(tmp_path, monkeypatch):
    monkeypatch.setattr(updates, "__version__", "0.1.0")
    source = tmp_path / "src O'Brien"
    source.mkdir()
    manifest = tmp_path / "state" / "install-manifest.json"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({"source": str(source), "app": "codex"}), encoding="utf-8")
    monkeypatch.setattr(updates, "manifest_path", lambda env: manifest)
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if "fetch" in command:
            return subprocess.CompletedProcess(command, 0, "", "")
        if "tag" in command:
            return subprocess.CompletedProcess(command, 0, "v0.9.0\nv0.10.0\nv1.0.0-rc1\nvfoo\n", "")
        return subprocess.CompletedProcess(command, 0,
            "## [Unreleased]\n\n## [0.10.0] - 2026-01-02\n\n### Added\n\n- Nuevo cambio.\n", "")

    result = updates.check_update(env={}, run=run, which=lambda name: "/usr/bin/git", system="Linux")
    assert result["installed"] == "0.1.0"
    assert result["latest"] == "0.10.0"
    assert result["update_available"] is True
    assert result["changes"] == [{"version": "0.10.0", "date": "2026-01-02",
                                   "text": "### Added\n\n- Nuevo cambio."}]
    assert result["command"] == (f"LITMAN_APP=codex LITMAN_SRC_DIR={shlex.quote(str(source))} sh "
                                  f"{shlex.quote(str(source) + '/harness/deployment/install.sh')}")
    assert all(kwargs["encoding"] == "utf-8" for _, kwargs in calls)


def test_check_update_powershell_quotes_custom_path(tmp_path, monkeypatch):
    monkeypatch.setattr(updates, "__version__", "0.1.0")
    manifest = tmp_path / "manifest.json"
    source = "C:\\Users\\O'Brien Smith\\LitMan"
    manifest.write_text(json.dumps({"source": source, "app": "codex"}), encoding="utf-8")
    monkeypatch.setattr(updates, "manifest_path", lambda env: manifest)
    outputs = iter(("", "v0.2.0\n", "## [0.2.0] - 2026-01-02\n\n### Added\n\n- Change.\n"))
    result = updates.check_update(env={}, run=lambda command, **kwargs:
                                  subprocess.CompletedProcess(command, 0, next(outputs), ""),
                                  which=lambda name: "git", system="Windows")
    assert "O''Brien Smith" in result["command"]
    assert "-ExecutionPolicy Bypass -File 'C:\\Users\\O''Brien Smith\\LitMan\\harness\\deployment\\install.ps1'" in result["command"]


def test_check_update_has_no_command_when_no_tag_or_newer_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(updates, "__version__", "0.1.0")
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"source":"/src","app":"claude"}', encoding="utf-8")
    monkeypatch.setattr(updates, "manifest_path", lambda env: manifest)
    outputs = iter(("", "v0.1.0\nv0.0.9\n"))
    result = updates.check_update(env={}, run=lambda command, **kwargs:
                                  subprocess.CompletedProcess(command, 0, next(outputs), ""),
                                  which=lambda name: "git", system="Darwin")
    assert result["latest"] == "0.1.0" and result["update_available"] is False
    assert result["changes"] == [] and result["command"] is None


def test_check_update_reports_missing_source_and_git_failure(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    monkeypatch.setattr(updates, "manifest_path", lambda env: manifest)
    with pytest.raises(HarnessError) as missing:
        updates.check_update(env={})
    assert missing.value.code == "update_source_missing"
    manifest.write_text('{"source":"/src"}', encoding="utf-8")
    with pytest.raises(HarnessError) as failed:
        updates.check_update(env={}, which=lambda name: None)
    assert failed.value.code == "update_check_failed"
