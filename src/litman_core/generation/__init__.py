"""Generación de entregables."""

from .service import generate_documents
from .registry import ARTIFACT_GENERATORS, resolve_artifact_generators

__all__ = ["ARTIFACT_GENERATORS", "generate_documents", "resolve_artifact_generators"]
