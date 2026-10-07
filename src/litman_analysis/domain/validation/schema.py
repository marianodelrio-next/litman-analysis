from __future__ import annotations

from jsonschema import Draft202012Validator

from .models import ValidationError


def validate_schema(data: dict, schema: dict) -> list[ValidationError]:
    """Devuelve los incumplimientos del JSON Schema sin mezclar otras reglas."""
    return [
        {"path": ".".join(map(str, error.path)), "message": error.message}
        for error in Draft202012Validator(schema).iter_errors(data)
    ]
