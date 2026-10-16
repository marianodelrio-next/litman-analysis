from .codex_cli import CodexProvider
from .codex_auth import CodexAuthentication
from .claude_code import ClaudeCodeProvider
from .resolution import resolve_llm

def build_provider(settings, job):
    provider, model = resolve_llm(settings)
    if provider == "claude-code":
        return ClaudeCodeProvider(binary=settings.claude_binary, model=model, timeout_seconds=settings.llm_timeout_seconds, config_dir=settings.claude_config_dir)
    if provider != "codex": raise ValueError(f"Proveedor LLM no admitido: {provider}")
    auth = CodexAuthentication.from_environment(codex_home=settings.codex_home_dir)
    return CodexProvider(binary=settings.codex_binary, model=model, timeout_seconds=settings.llm_timeout_seconds, authentication=auth, home=settings.home_dir, codex_home=settings.codex_home_dir, tool_failure_policy="warn")
