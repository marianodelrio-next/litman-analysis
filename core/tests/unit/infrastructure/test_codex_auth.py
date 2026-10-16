from pathlib import Path
import pytest
from litman_core.infrastructure.llm.codex_auth import CodexAuthentication, CodexAuthenticationError

def secret(tmp_path: Path, value: str = "secret") -> Path:
    path = tmp_path / "secret"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value + "\n", encoding="utf-8")
    return path

def chatgpt_home(tmp_path: Path) -> Path:
    home = tmp_path / "codex"
    home.mkdir(parents=True)
    auth = home / "auth.json"
    auth.write_text('{"tokens":"test-only"}', encoding="utf-8")
    auth.chmod(0o600)
    return home

def test_chatgpt_uses_private_persistent_state(tmp_path):
    auth = CodexAuthentication.from_environment(
        {"LITMAN_CORE_CODEX_AUTH_MODE": "chatgpt"},
        codex_home=chatgpt_home(tmp_path),
    )
    assert auth.mode == "chatgpt"
    assert auth.cli_login_method == "chatgpt"
    assert auth.environment() == {}

def test_chatgpt_is_default(tmp_path):
    assert CodexAuthentication.from_environment(
        {}, codex_home=chatgpt_home(tmp_path)
    ).mode == "chatgpt"

def test_chatgpt_requires_auth_file(tmp_path):
    home = tmp_path / "codex"; home.mkdir()
    with pytest.raises(CodexAuthenticationError, match="auth.json") as exc_info:
        CodexAuthentication.from_environment({}, codex_home=home)
    assert exc_info.value.code == "llm_unavailable"

def test_chatgpt_rejects_unsafe_auth_permissions(tmp_path):
    home = chatgpt_home(tmp_path)
    (home / "auth.json").chmod(0o644)
    with pytest.raises(CodexAuthenticationError, match="0600"):
        CodexAuthentication.from_environment({}, codex_home=home)

def test_api_key_only(tmp_path):
    auth = CodexAuthentication.from_environment({
        "LITMAN_CORE_CODEX_AUTH_MODE": "api-key",
        "LITMAN_CORE_CODEX_API_KEY_FILE": str(secret(tmp_path)),
    })
    assert auth.environment() == {"CODEX_API_KEY": "secret"}
    assert auth.cli_login_method == "api"

def test_unsupported_mode_fails():
    with pytest.raises(CodexAuthenticationError):
        CodexAuthentication.from_environment({"LITMAN_CORE_CODEX_AUTH_MODE": "other"})

def test_api_key_requires_existing_file():
    with pytest.raises(CodexAuthenticationError):
        CodexAuthentication.from_environment({"LITMAN_CORE_CODEX_AUTH_MODE": "api-key"})

def test_mixed_supported_modes_fail(tmp_path):
    with pytest.raises(CodexAuthenticationError, match="mezcla"):
        CodexAuthentication.from_environment({
            "LITMAN_CORE_CODEX_AUTH_MODE": "chatgpt",
            "LITMAN_CORE_CODEX_API_KEY_FILE": str(secret(tmp_path)),
        }, codex_home=chatgpt_home(tmp_path / "state"))
