"""Single operation registry shared by CLI and MCP.

Each operation has a name, a description stating whether it is a query or a
mutation, a JSON Schema for its arguments and a handler.  ``invoke`` returns the
common envelope ``{"ok": true, "result": ...}`` or
``{"ok": false, "error": {"code", "message", "details"}}``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ...errors import HarnessError, safe_exception_message

ServicesFactory = Callable[[], Any]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[["Context", dict[str, Any]], Any]
    mutates: bool = False

    def descriptor(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "inputSchema": self.input_schema}


class Context:
    """Builds services lazily, once per invocation, so listing never needs configuration."""

    def __init__(self, factory: ServicesFactory):
        self._factory = factory
        self._services: Any = None

    def services(self) -> Any:
        if self._services is None:
            self._services = self._factory()
        return self._services


def schema(properties: dict[str, Any] | None = None, required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"type": "object", "properties": properties or {}, "required": list(required),
            "additionalProperties": False}


_REGISTRY: dict[str, Tool] | None = None


def registry() -> dict[str, Tool]:
    global _REGISTRY
    if _REGISTRY is None:
        from . import analysis, dossier, setup
        tools = (*dossier.TOOLS, *analysis.TOOLS, *setup.TOOLS)
        _REGISTRY = {tool.name: tool for tool in tools}
        if len(_REGISTRY) != len(tools):
            raise RuntimeError("Nombres de operación duplicados")
    return _REGISTRY


def tool_descriptors() -> list[dict[str, Any]]:
    return [tool.descriptor() for tool in registry().values()]


_TYPES: dict[str, Callable[[Any], bool]] = {
    "string": lambda value: isinstance(value, str),
    "array": lambda value: isinstance(value, list),
    "object": lambda value: isinstance(value, dict),
    "boolean": lambda value: isinstance(value, bool),
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
}


def validate_arguments(input_schema: dict[str, Any], args: Any) -> None:
    """Small deterministic subset: object, required, known properties, basic types, enum, array items."""
    if not isinstance(args, dict):
        raise HarnessError("invalid_request", "Los argumentos deben ser un objeto JSON")
    properties: dict[str, Any] = input_schema.get("properties", {})
    missing = [name for name in input_schema.get("required", []) if name not in args]
    if missing:
        raise HarnessError("invalid_request", "Faltan argumentos obligatorios", details={"missing": missing})
    unknown = sorted(name for name in args if name not in properties)
    if unknown and input_schema.get("additionalProperties") is False:
        raise HarnessError("invalid_request", "Argumentos no admitidos", details={"unknown": unknown})
    for name, value in args.items():
        _validate_value(name, properties.get(name, {}), value)


def _validate_value(name: str, spec: dict[str, Any], value: Any) -> None:
    expected = spec.get("type")
    if expected and not _TYPES[expected](value):
        raise HarnessError("invalid_request", f"El argumento {name} debe ser de tipo {expected}",
                           details={"argument": name, "expected": expected})
    if "enum" in spec and value not in spec["enum"]:
        raise HarnessError("invalid_request", f"Valor no admitido para {name}",
                           details={"argument": name, "allowed": spec["enum"]})
    if expected == "array" and "items" in spec:
        for item in value:
            _validate_value(f"{name}[]", spec["items"], item)
    if expected == "object" and isinstance(spec.get("additionalProperties"), dict):
        for key, item in value.items():
            _validate_value(f"{name}.{key}", spec["additionalProperties"], item)


def error_envelope(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, "details": details or {}}}


def invoke(name: str, args: Any, services_factory: ServicesFactory | None = None) -> dict[str, Any]:
    tool = registry().get(name)
    if tool is None:
        return error_envelope("unknown_operation", "Operación no admitida", {"operation": name})
    if services_factory is None:
        from ..assembly import build_services
        services_factory = build_services
    try:
        validate_arguments(tool.input_schema, args)
        result = tool.handler(Context(services_factory), args)
    except HarnessError as exc:
        return error_envelope(exc.code, str(exc), exc.details)
    except Exception as exc:  # noqa: BLE001 - transports must always answer with the envelope
        return error_envelope("internal_error", "Fallo inesperado del harness",
                              {"error": safe_exception_message(exc)})
    return {"ok": True, "result": result}
