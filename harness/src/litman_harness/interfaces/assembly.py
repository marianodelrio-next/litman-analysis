"""Builds the shared services from local configuration; never from transport input."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Callable, Mapping

from ..adapters import core
from ..adapters.drive import DriveGateway, GoogleDriveGateway
from ..adapters.drive_state import DriveSharedState
from ..adapters.metadata import MetadataGateway
from ..adapters.oauth import DesktopOAuthProvider
from ..analysis.service import AnalysisService
from ..dossier.publication import PublicationService
from ..dossier.service import ExpedienteService
from ..dossier.summary import SummaryService
from ..dossier.shared_state import SharedStateCapability, UnavailableSharedState
from ..errors import HarnessError, safe_exception_message
from ..local_paths import CONFIGURABLE, METADATA_ENV, client_path, plan_store_root, token_path, work_root
from ..plans import PlanStore


@dataclass(frozen=True)
class Services:
    adapter: str
    drive: DriveGateway
    shared_state: SharedStateCapability
    expediente: ExpedienteService
    analysis: AnalysisService
    publication: PublicationService
    summary: SummaryService


def adapter_kind(env: Mapping[str, str]) -> str:
    """Development metadata when explicitly configured; personal OAuth otherwise."""
    return "metadata" if env.get(METADATA_ENV) else "oauth"


def oauth_provider(env: Mapping[str, str] | None = None) -> DesktopOAuthProvider:
    env = os.environ if env is None else env
    return DesktopOAuthProvider(token_path(env), client_path(env))


def _authorized_session(credentials: Any) -> Any:
    from google.auth.transport.requests import AuthorizedSession
    return AuthorizedSession(credentials)


def build_services(env: Mapping[str, str] | None = None, *, provider: DesktopOAuthProvider | None = None,
                   session_factory: Callable[[Any], Any] = _authorized_session) -> Services:
    """One gateway, plan store and shared state for every service.

    OAuth writes shared state through Drive v2 ``If-Match``; development
    metadata stays read-only (``pending_concurrency_gate``).
    """
    env = os.environ if env is None else env
    kind = adapter_kind(env)
    store = PlanStore(plan_store_root(env))
    work = work_root(env)
    shared_state: SharedStateCapability
    if kind == "metadata":
        drive: DriveGateway = MetadataGateway(Path(env[METADATA_ENV]))
        shared_state = UnavailableSharedState()
    else:
        provider = provider or oauth_provider(env)
        drive = GoogleDriveGateway(provider.drive_service())
        shared_state = DriveSharedState(session_factory(provider.authorized_credentials()), drive)
    expediente = ExpedienteService(drive, store, shared_state)
    publication = PublicationService(expediente, work)
    analysis = AnalysisService(drive, store, work_root=work, publication=publication)
    return Services(kind, drive, shared_state, expediente, analysis, publication, SummaryService(expediente))


def diagnose(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Configuration report without tokens, secrets or local paths."""
    env = os.environ if env is None else env
    kind = adapter_kind(env)
    report: dict[str, Any] = {
        "adapter": kind,
        "read_only": kind == "metadata",
        "token_exposed": False,
        "identity": None,
        "oauth": None,
        "core_executable_found": core.core_executable() is not None,
        "shared_state": {"available": False, "mechanism": "unavailable"},
        "paths_configured": {name: bool(env.get(name)) for name in CONFIGURABLE},
        "errors": [],
    }
    if kind == "oauth":
        try:
            report["oauth"] = oauth_provider(env).diagnose()
        except HarnessError as exc:
            report["errors"].append({"code": exc.code, "message": str(exc)})
        else:
            # No session is opened here: availability follows from usable credentials.
            usable = "error" not in report["oauth"]
            report["shared_state"] = {"available": usable,
                                      "mechanism": "drive_v2_if_match" if usable else "unavailable"}
    try:
        report["identity"] = build_services(env).expediente.identity()
    except HarnessError as exc:
        if not any(item["code"] == exc.code for item in report["errors"]):
            report["errors"].append({"code": exc.code, "message": str(exc)})
    except Exception as exc:  # noqa: BLE001 - diagnostics must report, not crash
        report["errors"].append({"code": "identity_unavailable", "message": safe_exception_message(exc)})
    return report
