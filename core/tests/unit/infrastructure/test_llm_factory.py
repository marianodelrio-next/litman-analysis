from dataclasses import replace

from litman_core.config import Settings
from litman_core.infrastructure.llm.factory import build_provider


def test_codex_provider_uses_llm_timeout_and_resolved_model():
    settings = replace(Settings(), llm_provider="codex", llm_model="gpt-5.6-luna", llm_timeout_seconds=42)
    provider = build_provider(settings, job=None)
    assert provider.model == "gpt-5.6-luna"
    assert provider.timeout_seconds == 42


def test_claude_code_provider_uses_llm_timeout_and_resolved_model():
    settings = replace(Settings(), llm_provider="claude-code", llm_model="claude-sonnet-5", llm_timeout_seconds=42)
    provider = build_provider(settings, job=None)
    assert provider.model == "claude-sonnet-5"
    assert provider.timeout_seconds == 42
