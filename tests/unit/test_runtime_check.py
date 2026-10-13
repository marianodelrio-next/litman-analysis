from pathlib import Path

from litman_core import runtime_check


def test_auth_check_does_not_create_or_read_state(tmp_path, monkeypatch):
    state = tmp_path / "codex"
    monkeypatch.setenv("LITMAN_CORE_CODEX_AUTH_MODE", "chatgpt")
    assert runtime_check._auth_state(state) is False
    assert not state.exists()
