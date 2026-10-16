from __future__ import annotations

import json
import subprocess

import pytest

from litman_harness.errors import HarnessError
from litman_harness.local_paths import settings_path
from litman_harness.settings import load_settings, setup


def _info_run(contract=1, providers=("codex", "claude-code"), version="0.1.0"):
    def run(command, **kwargs):
        if command[-1] == "info":
            return subprocess.CompletedProcess(command, 0, json.dumps(
                {"contract": contract, "version": version, "providers": list(providers)}), "")
        raise AssertionError("unexpected command")
    return run


def test_setup_persists_provider_and_model_under_isolated_config_home(harness_env, monkeypatch, tmp_path):
    from litman_harness.adapters import core
    executable = tmp_path / "bin" / "litman-core"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text("#!/bin/sh\n"); executable.chmod(0o755)
    monkeypatch.setattr(core.sysconfig, "get_path", lambda name: str(tmp_path / "bin"))

    result = setup(harness_env, "codex", "gpt-5.6-luna", run=_info_run())
    assert result == {"provider": "codex", "contract": 1, "core_version": "0.1.0", "model": "gpt-5.6-luna"}
    path = settings_path(harness_env)
    assert path.is_file()
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert load_settings(harness_env) == {"provider": "codex", "model": "gpt-5.6-luna"}


def test_setup_without_model_persists_only_provider(harness_env, monkeypatch, tmp_path):
    from litman_harness.adapters import core
    executable = tmp_path / "bin" / "litman-core"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text("#!/bin/sh\n"); executable.chmod(0o755)
    monkeypatch.setattr(core.sysconfig, "get_path", lambda name: str(tmp_path / "bin"))

    setup(harness_env, "codex", run=_info_run())
    assert load_settings(harness_env) == {"provider": "codex"}


def test_setup_rejects_mismatched_contract(harness_env, monkeypatch, tmp_path):
    from litman_harness.adapters import core
    executable = tmp_path / "bin" / "litman-core"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text("#!/bin/sh\n"); executable.chmod(0o755)
    monkeypatch.setattr(core.sysconfig, "get_path", lambda name: str(tmp_path / "bin"))

    with pytest.raises(HarnessError) as raised:
        setup(harness_env, "codex", run=_info_run(contract=2))
    assert raised.value.code == "core_incompatible"


def test_setup_rejects_provider_not_offered_by_core(harness_env, monkeypatch, tmp_path):
    from litman_harness.adapters import core
    executable = tmp_path / "bin" / "litman-core"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text("#!/bin/sh\n"); executable.chmod(0o755)
    monkeypatch.setattr(core.sysconfig, "get_path", lambda name: str(tmp_path / "bin"))

    with pytest.raises(HarnessError) as raised:
        setup(harness_env, "claude-code", run=_info_run(providers=("codex",)))
    assert raised.value.code == "invalid_provider"


def test_setup_without_core_installed_reports_core_not_installed(harness_env, monkeypatch, tmp_path):
    from litman_harness.adapters import core
    monkeypatch.setattr(core.sysconfig, "get_path", lambda name: str(tmp_path / "bin"))
    monkeypatch.setenv("PATH", str(tmp_path / "other-bin"))

    with pytest.raises(HarnessError) as raised:
        setup(harness_env, "codex")
    assert raised.value.code == "core_not_installed"


def test_load_settings_returns_none_when_unset(harness_env):
    assert load_settings(harness_env) is None


def test_load_settings_rejects_malformed_toml(harness_env):
    path = settings_path(harness_env)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text("not valid toml =", encoding="utf-8")
    with pytest.raises(HarnessError) as raised:
        load_settings(harness_env)
    assert raised.value.code == "invalid_settings"


def test_load_settings_rejects_missing_provider(harness_env):
    path = settings_path(harness_env)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text('model = "x"\n', encoding="utf-8")
    with pytest.raises(HarnessError) as raised:
        load_settings(harness_env)
    assert raised.value.code == "invalid_settings"
