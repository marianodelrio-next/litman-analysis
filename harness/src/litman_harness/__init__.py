"""Local adapters for an explicitly selected LitMan Drive expediente.

This package deliberately does not import ``litman_core`` or its service-account
Drive publisher.  It is a separate user-OAuth client.
"""

from .models import HarnessError, Manifest, Plan
from .service import ExpedienteService

__version__ = "0.1.0"

__all__ = ["ExpedienteService", "HarnessError", "Manifest", "Plan"]
