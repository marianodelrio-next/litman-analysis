"""Local adapters for an explicitly selected LitMan Drive expediente.

This package deliberately does not import ``litman_core`` or its service-account
Drive publisher.  It is a separate user-OAuth client.
"""

from .errors import HarnessError

__version__ = "0.1.0"

__all__ = ["HarnessError", "__version__"]
