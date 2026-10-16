"""Desktop OAuth for each employee: login, private token storage and refresh.

Tokens and client files live in the user profile, never in the checkout, the
transports, the manifest or logs.  Only the ``drive`` scope is requested: Google
grants the person's own access, and the harness itself limits every operation
to the connected dossier tree (``drive.file`` cannot open existing folders by ID).
"""
from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any, Callable

from ..errors import HarnessError
from ..local_paths import ensure_outside_checkout

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
SCOPES = [DRIVE_SCOPE]


def _load_credentials(path: Path) -> Any:
    # Without explicit scopes google-auth keeps the scopes actually granted to the token.
    from google.oauth2.credentials import Credentials
    return Credentials.from_authorized_user_file(str(path))


def _refresh_request() -> Any:
    from google.auth.transport.requests import Request
    return Request()


def _installed_app_flow(client_path: Path, scopes: list[str]) -> Any:
    from google_auth_oauthlib.flow import InstalledAppFlow
    return InstalledAppFlow.from_client_secrets_file(str(client_path), scopes=scopes)


def write_private(path: Path, content: str) -> None:
    """Write a 0600 file atomically inside a 0700 directory."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
    if platform.system() != "Windows":
        os.chmod(temporary, 0o600)
    temporary.replace(path)


class DesktopOAuthProvider:
    """Loads, refreshes and stores a user token from a private profile location.

    Tests inject ``credentials``, ``loader``, ``request_factory``, ``flow_factory``
    or ``service_factory``; the default implementations use Google libraries.
    """

    def __init__(self, token_path: Path, client_path: Path | None = None, *, credentials: Any | None = None,
                 loader: Callable[[Path], Any] = _load_credentials,
                 request_factory: Callable[[], Any] = _refresh_request,
                 flow_factory: Callable[[Path, list[str]], Any] = _installed_app_flow,
                 service_factory: Callable[[Any], Any] | None = None):
        self.token_path = ensure_outside_checkout(token_path, "unsafe_token_path",
                                                  "El token OAuth debe guardarse fuera del clon")
        self.client_path = (ensure_outside_checkout(client_path, "unsafe_client_path",
                                                    "El cliente OAuth debe guardarse fuera del clon")
                            if client_path is not None else None)
        self.credentials = credentials
        self.loader = loader
        self.request_factory = request_factory
        self.flow_factory = flow_factory
        self.service_factory = service_factory

    def login(self) -> dict[str, Any]:
        """Interactive desktop login (CLI only); stores the token privately."""
        if self.client_path is None or not self.client_path.is_file():
            raise HarnessError("oauth_client_missing",
                               "Falta el cliente OAuth de escritorio (LITMAN_HARNESS_OAUTH_CLIENT)")
        flow = self.flow_factory(self.client_path, SCOPES)
        credentials = flow.run_local_server(port=0)
        write_private(self.token_path, credentials.to_json())
        self.credentials = credentials
        return {"logged_in": True, "scopes": sorted(getattr(credentials, "scopes", None) or SCOPES),
                "token_exposed": False}

    def drive_service(self) -> Any:
        credentials = self._credentials()
        if self.service_factory:
            return self.service_factory(credentials)
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=credentials, cache_discovery=False)

    def authorized_credentials(self) -> Any:
        """Valid user credentials, refreshed and persisted when needed."""
        return self._credentials()

    def _credentials(self) -> Any:
        if self.credentials is None:
            if not self.token_path.is_file():
                raise HarnessError("oauth_login_required", "No hay token OAuth local; ejecute `litman login`")
            try:
                self.credentials = self.loader(self.token_path)
            except Exception as exc:
                raise HarnessError("oauth_token_invalid", "El token OAuth local no es utilizable") from exc
        credentials = self.credentials
        granted = set(getattr(credentials, "scopes", None) or ())
        if not set(SCOPES) <= granted:
            raise HarnessError("oauth_scope_missing",
                               "El token se concedió con otro permiso de Drive; ejecute `litman login` de nuevo",
                               details={"required_scopes": SCOPES, "granted_scopes": sorted(granted)})
        if not credentials.valid:
            if not (getattr(credentials, "expired", False) and getattr(credentials, "refresh_token", None)):
                raise HarnessError("oauth_login_required", "El token OAuth debe renovarse con `litman login`")
            try:
                credentials.refresh(self.request_factory())
            except Exception as exc:
                raise HarnessError("oauth_login_required",
                                   "No se pudo refrescar el token OAuth; ejecute `litman login`") from exc
            write_private(self.token_path, credentials.to_json())
        return credentials

    def diagnose(self) -> dict[str, object]:
        report: dict[str, object] = {"token_present": self.token_path.is_file(),
                                     "client_configured": bool(self.client_path and self.client_path.is_file()),
                                     "requested_scopes": SCOPES,
                                     "token_exposed": False}
        try:
            credentials = self._credentials()
        except HarnessError as exc:
            report["error"] = {"code": exc.code, "message": str(exc)}
            return report
        report["scopes"] = sorted(set(getattr(credentials, "scopes", None) or SCOPES))
        report["valid"] = bool(credentials.valid)
        return report
