"""Carga explícita y fusión de preferencias funcionales de generación."""
from __future__ import annotations

import copy
from typing import Any

DEFAULT_GENERATION: dict[str, Any] = {
    "technical_document": {"template_id": "next-standard-v1", "content_profile": "skeleton-v1", "output_language": "auto"},
    "economic_simulator": {"template_id": "standard-v1"},
}
_KEYS = {"technical_document", "economic_simulator"}
APPROVED_ARTIFACTS = frozenset({"technical-summary", "bid-preparation-guide", "technical-document", "economic-simulator"})
_TECHNICAL_KEYS = {"template_id", "content_profile", "output_language", "include_internal_pending", "include_editorial_guidance"}

def merge_generation(*layers: dict[str, Any] | None) -> dict[str, Any]:
    result = copy.deepcopy(DEFAULT_GENERATION)
    for layer in layers:
        if layer:
            result = _merge(result, _validate(layer))
    return result


def _validate(data: dict[str, Any]) -> dict[str, Any]:
    unknown = set(data) - _KEYS
    if unknown:
        raise ValueError(f"Claves de generación desconocidas: {', '.join(sorted(unknown))}")
    for name, allowed in (("technical_document", _TECHNICAL_KEYS), ("economic_simulator", {"template_id"})):
        value = data.get(name)
        if value is not None:
            if not isinstance(value, dict) or set(value) - allowed:
                raise ValueError(f"generation.{name} contiene claves o tipos inválidos")
            for key, item in value.items():
                if key.startswith("include_"):
                    if not isinstance(item, bool):
                        raise ValueError(f"generation.{name}.{key} debe ser booleano")
                elif not isinstance(item, str):
                    raise ValueError(f"generation.{name}.{key} debe ser texto")
    return copy.deepcopy(data)


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base
