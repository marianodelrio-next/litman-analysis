from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tomllib

import pytest

from litman_harness.adapters.core import core_config, run_core
from litman_harness.errors import HarnessError


def test_config_is_exact_local_job_without_drive_destination(tmp_path: Path):
    text = core_config(job_id="op-1", job_type="assessment", input_dir=tmp_path / "in",
                       output_dir=tmp_path / "out", provider="codex")
    assert tomllib.loads(text) == {
        "job": {"id": "op-1", "type": "assessment"},
        "input": {"kind": "local", "location": str(tmp_path / "in")},
        "output": {"directory": str(tmp_path / "out")},
        "publication": {"include_run_files": False},
        "llm": {"provider": "codex"},
    }
    assert "google_drive_folder_id" not in text


def test_config_rejects_unknown_provider(tmp_path: Path):
    with pytest.raises(HarnessError) as raised:
        core_config(job_id="op", job_type="assessment", input_dir=tmp_path, output_dir=tmp_path, provider="other")
    assert raised.value.code == "invalid_provider"


@pytest.mark.parametrize(("returncode", "stdout", "code"), (
    (1, "", "core_failed"),
    (0, "not json", "invalid_core_result"),
    (0, json.dumps({"status": "failed"}), "invalid_core_result"),
))
def test_run_core_rejects_failed_or_unvalidated_results(tmp_path: Path, returncode: int, stdout: str, code: str):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, returncode, stdout, "boom")

    with pytest.raises(HarnessError) as raised:
        run_core(tmp_path / "config.toml", run)
    assert raised.value.code == code
    assert calls == [["litman-core", "run", "--config", str(tmp_path / "config.toml")]]


def test_configured_core_executable_is_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from litman_harness.adapters.core import core_executable, core_version
    executable = tmp_path / "bin" / "litman-core"
    monkeypatch.setenv("LITMAN_HARNESS_CORE", str(executable))
    assert core_executable() is None
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o755)
    assert core_executable() == str(executable)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "litman-core 0.2.0", "")

    assert core_version(run) == "0.2.0"
    with pytest.raises(HarnessError):
        run_core(tmp_path / "config.toml", run)
    assert calls == [[str(executable), "--version"],
                     [str(executable), "run", "--config", str(tmp_path / "config.toml")]]
