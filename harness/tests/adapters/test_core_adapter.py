from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import tomllib

import pytest

from litman_harness.adapters.core import CORE_ERROR_MESSAGES, core_config, core_info, run_core
from litman_harness.errors import HarnessError

CONTRACTS = Path(__file__).parents[3] / "docs" / "contracts"
EXAMPLES = CONTRACTS / "examples"
MINIMAL_TOML = CONTRACTS / "core-config.minimal.toml"


def test_config_is_exact_minimal_template_without_drive_destination(tmp_path: Path):
    text = core_config(job_type="assessment", input_dir=tmp_path / "in",
                       output_dir=tmp_path / "out", provider="codex")
    assert tomllib.loads(text) == {
        "job": {"type": "assessment"},
        "input": {"location": str(tmp_path / "in")},
        "output": {"directory": str(tmp_path / "out")},
        "llm": {"provider": "codex"},
    }
    assert "google_drive_folder_id" not in text
    assert "id" not in tomllib.loads(text)["job"]
    assert "kind" not in tomllib.loads(text)["input"]
    assert "publication" not in tomllib.loads(text)


def test_config_keys_match_the_minimal_contract_template(tmp_path: Path):
    text = core_config(job_type="assessment", input_dir=tmp_path / "in",
                       output_dir=tmp_path / "out", provider="codex")
    produced = tomllib.loads(text)
    expected = tomllib.loads(MINIMAL_TOML.read_text(encoding="utf-8"))

    def keys(data: dict) -> set[str]:
        return {f"{table}.{key}" for table, values in data.items() for key in values}

    assert keys(produced) == keys(expected)


def test_config_includes_model_only_when_given(tmp_path: Path):
    without_model = tomllib.loads(core_config(job_type="assessment", input_dir=tmp_path, output_dir=tmp_path, provider="codex"))
    assert "model" not in without_model["llm"]
    with_model = tomllib.loads(core_config(job_type="assessment", input_dir=tmp_path, output_dir=tmp_path, provider="claude-code", model="claude-sonnet-5"))
    assert with_model["llm"]["model"] == "claude-sonnet-5"


def test_config_rejects_unknown_provider(tmp_path: Path):
    with pytest.raises(HarnessError) as raised:
        core_config(job_type="assessment", input_dir=tmp_path, output_dir=tmp_path, provider="other")
    assert raised.value.code == "invalid_provider"


def _runner(returncode: int, stdout: str, stderr: str = "boom"):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)

    return run, calls


@pytest.mark.parametrize("name", sorted(p.stem for p in EXAMPLES.glob("success-*.json")))
def test_run_core_returns_the_payload_for_each_success_example(tmp_path: Path, name: str):
    stdout = (EXAMPLES / f"{name}.json").read_text(encoding="utf-8")
    run, calls = _runner(0, stdout)
    payload = run_core(tmp_path / "config.toml", run)
    assert payload["status"] == "succeeded"
    assert calls[0][1:] == ["run", "--config", str(tmp_path / "config.toml")]
    assert calls[0][0].endswith("/litman-core")


@pytest.mark.parametrize("code", sorted(CORE_ERROR_MESSAGES))
def test_run_core_reports_core_failed_for_each_error_code(tmp_path: Path, code: str):
    stdout = (EXAMPLES / f"failed-{code}.json").read_text(encoding="utf-8")
    run, _ = _runner(1, stdout)
    with pytest.raises(HarnessError) as raised:
        run_core(tmp_path / "config.toml", run)
    assert raised.value.code == "core_failed"
    assert raised.value.details["code"] == code
    assert str(raised.value) == CORE_ERROR_MESSAGES[code]


def test_run_core_rejects_mismatched_contract(tmp_path: Path):
    run, _ = _runner(0, json.dumps({"contract": 2, "status": "succeeded"}))
    with pytest.raises(HarnessError) as raised:
        run_core(tmp_path / "config.toml", run)
    assert raised.value.code == "core_incompatible"


def test_run_core_rejects_non_json_stdout(tmp_path: Path):
    run, _ = _runner(1, "not json")
    with pytest.raises(HarnessError) as raised:
        run_core(tmp_path / "config.toml", run)
    assert raised.value.code == "core_crashed"
    assert "boom" in raised.value.details["stderr"]


def test_run_core_treats_unknown_error_code_as_internal_message(tmp_path: Path):
    stdout = json.dumps({"contract": 1, "status": "failed", "error": {"code": "not_a_real_code", "message": "x"}})
    run, _ = _runner(1, stdout)
    with pytest.raises(HarnessError) as raised:
        run_core(tmp_path / "config.toml", run)
    assert str(raised.value) == CORE_ERROR_MESSAGES["internal"]
    assert raised.value.details["code"] == "not_a_real_code"


def test_run_core_rejects_unvalidated_success_payload(tmp_path: Path):
    run, _ = _runner(0, json.dumps({"contract": 1, "status": "succeeded"}))
    with pytest.raises(HarnessError) as raised:
        run_core(tmp_path / "config.toml", run)
    assert raised.value.code == "invalid_core_result"


def test_core_executable_is_resolved_beside_the_harness_interpreter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from litman_harness.adapters import core
    from litman_harness.adapters.core import core_executable
    executable = tmp_path / "bin" / "litman-core"
    monkeypatch.setattr(core.sysconfig, "get_path", lambda name: str(tmp_path / "bin"))
    assert core_executable() is None
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o755)
    assert core_executable() == str(executable)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, json.dumps({"contract": 1, "version": "0.2.0", "providers": ["codex", "claude-code"]}), "")

    assert core.core_info(run) == {"contract": 1, "version": "0.2.0", "providers": ["codex", "claude-code"]}
    with pytest.raises(HarnessError) as raised:
        core.run_core(tmp_path / "config.toml", run)
    assert raised.value.code == "invalid_core_result"
    assert calls == [[str(executable), "info"],
                     [str(executable), "run", "--config", str(tmp_path / "config.toml")]]


def test_core_info_returns_none_when_binary_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from litman_harness.adapters import core
    monkeypatch.setattr(core.sysconfig, "get_path", lambda name: str(tmp_path / "bin"))
    monkeypatch.setenv("PATH", str(tmp_path / "other-bin"))
    assert core_info() is None


def test_missing_core_is_reported_without_falling_back_to_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from litman_harness.adapters import core

    monkeypatch.setattr(core.sysconfig, "get_path", lambda name: str(tmp_path / "bin"))
    monkeypatch.setenv("PATH", str(tmp_path / "other-bin"))
    assert core.core_executable() is None
    with pytest.raises(HarnessError) as raised:
        core.run_core(tmp_path / "config.toml")
    assert raised.value.code == "core_not_installed"


def test_windows_uses_exe_without_posix_execute_bits_and_sets_utf8(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from litman_harness.adapters import core
    executable = tmp_path / "bin" / "litman-core.exe"
    executable.parent.mkdir()
    executable.write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(core.sysconfig, "get_path", lambda name: str(tmp_path / "bin"))
    monkeypatch.setattr(core.platform, "system", lambda: "Windows")
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, json.dumps(
            {"contract": 1, "version": "versión-á", "providers": ["codex"]}), "")

    assert core.core_executable() == str(executable)
    assert core.core_info(run)["version"] == "versión-á"
    assert calls[0][0][0].endswith("litman-core.exe")
    assert calls[0][1]["encoding"] == "utf-8"


@pytest.mark.skipif(sys.platform == "win32", reason="symlinked venv layout is POSIX-specific")
def test_core_command_finds_core_in_a_real_symlinked_venv(tmp_path: Path):
    """Reproduces the ``uv tool install`` layout: ``bin/python`` symlinks outside the venv."""
    env_dir = tmp_path / "env"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", "--symlinks", str(env_dir)],
                   check=True, capture_output=True, text=True)
    python = env_dir / "bin" / "python"
    assert python.is_symlink()
    assert Path(python).resolve().parent != env_dir / "bin"

    core_executable = env_dir / "bin" / "litman-core"
    core_executable.write_text("#!/bin/sh\necho hi\n")
    core_executable.chmod(0o755)

    harness_src = Path(__file__).parents[2] / "src"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(harness_src)
    code = "from litman_harness.adapters.core import core_executable; print(core_executable())"
    result = subprocess.run([str(python), "-c", code], capture_output=True, text=True, env=env, check=True)
    assert result.stdout.strip() == str(core_executable)
