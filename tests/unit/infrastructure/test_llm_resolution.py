from types import SimpleNamespace

from litman_core.infrastructure.llm.resolution import resolve_llm


def test_job_llm_settings_take_precedence_over_environment():
    settings = SimpleNamespace(llm_provider="codex", llm_model="env-model", codex_model="default", claude_model="sonnet")
    assert resolve_llm(settings, SimpleNamespace(llm_provider=None, llm_model=None)) == ("codex", "env-model")
    assert resolve_llm(settings, SimpleNamespace(llm_provider="claude-code", llm_model="opus")) == ("claude-code", "opus")


def test_provider_default_model_is_used_when_none_is_configured():
    codex = SimpleNamespace(llm_provider="codex", llm_model=None, codex_model="default", claude_model="sonnet")
    assert resolve_llm(codex) == ("codex", "default")
    claude = SimpleNamespace(llm_provider="claude-code", llm_model=None, codex_model="default", claude_model="sonnet")
    assert resolve_llm(claude) == ("claude-code", "sonnet")
