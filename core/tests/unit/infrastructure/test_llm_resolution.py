from types import SimpleNamespace

import pytest

from litman_core.config import Settings
from litman_core.infrastructure.llm.resolution import resolve_llm


def test_toml_selection_wins_over_defaults():
    job = SimpleNamespace(llm_provider="claude-code", llm_model="custom-model")
    assert resolve_llm(job) == ("claude-code", "custom-model")


def test_default_provider_and_model_without_toml_selection():
    job = SimpleNamespace(llm_provider=None, llm_model=None)
    assert resolve_llm(job) == ("codex", "gpt-5.6-luna")


def test_claude_code_default_model_is_sonnet_5():
    job = SimpleNamespace(llm_provider="claude-code", llm_model=None)
    assert resolve_llm(job) == ("claude-code", "claude-sonnet-5")


def test_removed_environment_variables_have_no_effect(monkeypatch):
    monkeypatch.setenv("LITMAN_CORE_LLM_PROVIDER", "claude-code")
    monkeypatch.setenv("LITMAN_CORE_LLM_MODEL", "from-env")
    monkeypatch.setenv("LITMAN_CORE_CLAUDE_MODEL", "from-env-claude")
    settings = Settings()
    assert resolve_llm(settings) == ("codex", "gpt-5.6-luna")


def test_settings_has_no_removed_fields():
    settings = Settings()
    for name in ("codex_model", "claude_model", "codex_timeout_seconds"):
        assert not hasattr(settings, name)


def test_unsupported_provider_is_rejected():
    with pytest.raises(ValueError):
        resolve_llm(SimpleNamespace(llm_provider="unknown", llm_model=None))
