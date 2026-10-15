"""Single source of truth for provider and model selection."""
from __future__ import annotations

from typing import Any


def resolve_llm(settings: Any, job: Any | None = None) -> tuple[str, str]:
    provider = getattr(job, "llm_provider", None) or getattr(settings, "llm_provider", None) or "codex"
    model = getattr(job, "llm_model", None) or getattr(settings, "llm_model", None)
    if model is None and provider == "codex":
        model = getattr(job, "codex_model", None)
    if model is None:
        model = (getattr(settings, "codex_model", None) if provider == "codex"
                 else getattr(settings, "claude_model", None))
    return provider, model or ("codex_default" if provider == "codex" else "claude_default")


def resolve_model(settings: Any, provider: str | None = None) -> str:
    """Resolve a model when the job-level legacy alias is unavailable."""
    provider = provider or getattr(settings, "llm_provider", None) or "codex"
    model = getattr(settings, "llm_model", None)
    if model is None:
        model = getattr(settings, "codex_model", None) if provider == "codex" else getattr(settings, "claude_model", None)
    return model or ("codex_default" if provider == "codex" else "claude_default")
