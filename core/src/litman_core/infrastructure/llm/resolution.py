"""Single source of truth for provider and model selection.

``resolve_llm`` accepts any object exposing ``llm_provider``/``llm_model``
(``JobRequest`` loaded from the TOML, or ``Settings`` once ``JobRunner`` has
copied the job's already-resolved selection into it with ``replace()``), so
the pipelines keep calling it with ``settings`` to read back the selection
``JobRunner`` resolved for this run.
"""
from __future__ import annotations

from typing import Any

from .providers import PROVIDERS


def resolve_llm(entity: Any) -> tuple[str, str]:
    provider = getattr(entity, "llm_provider", None) or "codex"
    if provider not in PROVIDERS:
        raise ValueError(f"Proveedor LLM no admitido: {provider}")
    model = getattr(entity, "llm_model", None) or PROVIDERS[provider].model
    return provider, model
