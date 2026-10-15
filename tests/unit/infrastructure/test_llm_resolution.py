from types import SimpleNamespace

from litman_core.infrastructure.llm.resolution import resolve_llm


def test_legacy_codex_model_does_not_override_environment_model():
    settings = SimpleNamespace(llm_provider="codex", llm_model="env-model", codex_model="default", claude_model=None)
    job = SimpleNamespace(llm_provider=None, llm_model=None, codex_model="legacy")
    assert resolve_llm(settings, job) == ("codex", "env-model")


def test_legacy_codex_model_is_used_only_for_codex():
    settings = SimpleNamespace(llm_provider="codex", llm_model=None, codex_model="default", claude_model="sonnet")
    assert resolve_llm(settings, SimpleNamespace(llm_provider=None, llm_model=None, codex_model="legacy")) == ("codex", "legacy")
    assert resolve_llm(SimpleNamespace(llm_provider="claude-code", llm_model=None, codex_model="default", claude_model="sonnet"),
                       SimpleNamespace(llm_provider=None, llm_model=None, codex_model="legacy")) == ("claude-code", "sonnet")
