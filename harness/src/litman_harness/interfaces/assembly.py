"""Builds the shared services from local configuration; never from transport input."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Callable, Mapping

from .. import installation
from .. import __version__
from ..adapters import core
from ..adapters.docs import DocsGateway, GoogleDocsGateway
from ..adapters.drive import DriveGateway, GoogleDriveGateway
from ..adapters.drive_state import DriveSharedState
from ..adapters.metadata import MetadataDocsGateway, MetadataGateway, MetadataSheetsGateway
from ..adapters.oauth import DesktopOAuthProvider
from ..adapters.sheets import GoogleSheetsGateway, SheetsGateway
from ..analysis.service import AnalysisService
from ..dossier.comments import CommentService
from ..dossier.documents import DocumentService
from ..dossier.file_changes import FileChangeService
from ..dossier.files import FileService
from ..dossier.publication import PublicationService
from ..dossier.service import ExpedienteService
from ..dossier.sheets import SheetsService
from ..dossier.summary import SummaryService
from ..dossier.shared_state import SharedStateCapability, UnavailableSharedState
from ..errors import HarnessError, safe_exception_message
from ..local_paths import CONFIGURABLE, METADATA_ENV, client_path, plan_store_root, token_path, work_root
from ..plans import PlanStore
from ..settings import load_settings

# An ID that no document has: a 404 proves the Docs API answers for this OAuth client.
DOCS_PROBE_ID = "litman-docs-api-probe-0000000000000000000000"
# An ID that no spreadsheet has: a 404 proves the Sheets API answers for this OAuth client.
SHEETS_PROBE_ID = "litman-sheets-api-probe-0000000000000000000000"


@dataclass(frozen=True)
class Services:
    adapter: str
    drive: DriveGateway
    shared_state: SharedStateCapability
    expediente: ExpedienteService
    analysis: AnalysisService
    publication: PublicationService
    summary: SummaryService
    docs: DocsGateway
    documents: DocumentService
    sheets: SheetsGateway
    sheet_edits: SheetsService
    files: FileService
    file_changes: FileChangeService
    comments: CommentService


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
        docs: DocsGateway = MetadataDocsGateway()
        sheets: SheetsGateway = MetadataSheetsGateway()
        shared_state = UnavailableSharedState()
    else:
        provider = provider or oauth_provider(env)
        drive = GoogleDriveGateway(provider.drive_service())
        docs = GoogleDocsGateway(provider.docs_service())
        sheets = GoogleSheetsGateway(provider.sheets_service())
        shared_state = DriveSharedState(session_factory(provider.authorized_credentials()), drive)
    expediente = ExpedienteService(drive, store, shared_state)
    publication = PublicationService(expediente, work)
    analysis = AnalysisService(drive, store, work_root=work, publication=publication,
                               settings=lambda: load_settings(env))
    documents = DocumentService(expediente, docs)
    comments = CommentService(expediente, documents)
    return Services(kind, drive, shared_state, expediente, analysis, publication, SummaryService(expediente), docs,
                    documents, sheets, SheetsService(expediente, sheets),
                    FileService(expediente, documents, sheets, comments), FileChangeService(expediente), comments)


def docs_api_status(docs: DocsGateway) -> str:
    """``enabled``, ``disabled`` or ``unknown`` from one read of a document that does not exist."""
    try:
        docs.get(DOCS_PROBE_ID)
    except HarnessError as exc:
        return {"not_found": "enabled", "docs_api_disabled": "disabled"}.get(exc.code, "unknown")
    except Exception:  # noqa: BLE001 - diagnostics must report, not crash
        return "unknown"
    return "enabled"


def sheets_api_status(sheets: SheetsGateway) -> str:
    """``enabled``, ``disabled`` or ``unknown`` from one read of a spreadsheet that does not exist."""
    try:
        sheets.get(SHEETS_PROBE_ID)
    except HarnessError as exc:
        return {"not_found": "enabled", "sheets_api_disabled": "disabled"}.get(exc.code, "unknown")
    except Exception:  # noqa: BLE001 - diagnostics must report, not crash
        return "unknown"
    return "enabled"


def diagnose(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Configuration report without tokens, secrets or local paths."""
    env = os.environ if env is None else env
    kind = adapter_kind(env)
    try:
        settings = load_settings(env)
    except HarnessError as exc:
        settings = None
        settings_error = {"code": exc.code, "message": str(exc)}
    else:
        settings_error = None
    info = core.core_info()
    report: dict[str, Any] = {
        "version": __version__,
        "adapter": kind,
        "read_only": kind == "metadata",
        "token_exposed": False,
        "identity": None,
        "oauth": None,
        "core_executable_found": core.core_executable() is not None,
        "shared_state": {"available": False, "mechanism": "unavailable"},
        "docs_api": "unknown",
        "sheets_api": "unknown",
        "paths_configured": {name: bool(env.get(name)) for name in CONFIGURABLE},
        "setup": {"configured": settings is not None,
                  "provider": settings.get("provider") if settings else None,
                  "model": settings.get("model") if settings else None},
        "core": {"contract": info.get("contract") if info else None,
                 "version": info.get("version") if info else None,
                 "compatible": info is not None and info.get("contract") == core.CONTRACT,
                 "environment": info.get("environment") if info else None},
        "installation": installation.status(env=env),
        "errors": [],
    }
    if settings_error is not None:
        report["errors"].append(settings_error)
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
    services = None
    try:
        services = build_services(env)
        report["identity"] = services.expediente.identity()
    except HarnessError as exc:
        if not any(item["code"] == exc.code for item in report["errors"]):
            report["errors"].append({"code": exc.code, "message": str(exc)})
    except Exception as exc:  # noqa: BLE001 - diagnostics must report, not crash
        report["errors"].append({"code": "identity_unavailable", "message": safe_exception_message(exc)})
    if services is not None:
        report["docs_api"] = docs_api_status(services.docs)
        report["sheets_api"] = sheets_api_status(services.sheets)
    return report
