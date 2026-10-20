from __future__ import annotations

from pathlib import Path

from litman_harness.adapters.docs import GoogleDocsGateway
from litman_harness.adapters.drive_state import DriveSharedState
from litman_harness.adapters.metadata import MetadataDocsGateway, MetadataSheetsGateway
from litman_harness.adapters.oauth import DesktopOAuthProvider
from litman_harness.adapters.sheets import GoogleSheetsGateway
from litman_harness.dossier.shared_state import UnavailableSharedState
from litman_harness.interfaces import assembly


class Credentials:
    valid = True
    scopes = ["https://www.googleapis.com/auth/drive"]


def test_oauth_assembly_writes_through_drive_v2_shared_state(unconfigured_env, tmp_path: Path, monkeypatch):
    sessions = []
    provider = DesktopOAuthProvider(tmp_path / "token.json", credentials=Credentials(),
                                    service_factory=lambda creds: object())
    services = assembly.build_services(provider=provider, session_factory=lambda creds: sessions.append(creds) or
                                       "session")
    assert isinstance(services.shared_state, DriveSharedState) and services.shared_state.session == "session"
    assert services.expediente.shared_state is services.shared_state and len(sessions) == 1
    assert services.adapter == "oauth"
    assert isinstance(services.docs, GoogleDocsGateway) and services.documents.docs is services.docs
    assert services.documents.dossier is services.expediente
    assert isinstance(services.sheets, GoogleSheetsGateway) and services.files.sheets is services.sheets
    assert services.files.documents is services.documents and services.files.dossier is services.expediente


def test_metadata_assembly_stays_read_only(harness_env):
    services = assembly.build_services()
    assert isinstance(services.shared_state, UnavailableSharedState)
    assert services.expediente.shared_state is services.shared_state
    assert isinstance(services.docs, MetadataDocsGateway) and services.documents.docs is services.docs
    assert isinstance(services.sheets, MetadataSheetsGateway) and services.files.sheets is services.sheets


def test_diagnose_reports_the_drive_mechanism_with_usable_oauth(unconfigured_env, monkeypatch):
    class Provider:
        def diagnose(self):
            return {"token_present": True, "valid": True, "token_exposed": False}

    monkeypatch.setattr(assembly, "oauth_provider", lambda env=None: Provider())
    monkeypatch.setattr(assembly, "build_services", lambda env=None: (_ for _ in ()).throw(RuntimeError("offline")))
    report = assembly.diagnose()
    assert report["shared_state"] == {"available": True, "mechanism": "drive_v2_if_match"}
    from litman_harness import __version__
    assert report["version"] == __version__


def test_diagnose_reports_setup_and_contract_without_configuration(unconfigured_env, monkeypatch):
    from litman_harness.adapters import core
    monkeypatch.setattr(core, "core_info", lambda run=None: None)
    monkeypatch.setattr(core, "core_executable", lambda: None)
    report = assembly.diagnose()
    assert report["setup"] == {"configured": False, "provider": None, "model": None}
    assert report["core"] == {"contract": None, "version": None, "compatible": False, "environment": None}
    assert "settings.toml" not in repr(report)


def test_diagnose_reports_installation_not_installed_without_a_manifest(unconfigured_env):
    report = assembly.diagnose()
    assert report["installation"] == {"installed": False}


def test_diagnose_reports_installation_and_core_environment(unconfigured_env, monkeypatch, tmp_path: Path):
    from litman_harness import installation
    from litman_harness.adapters import core

    monkeypatch.setattr(installation, "script_path", lambda name: tmp_path / "scripts" / name)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "home" / ".codex"))
    env = {"XDG_STATE_HOME": str(tmp_path / "state"), "XDG_CONFIG_HOME": str(tmp_path / "config"),
           "CODEX_HOME": str(tmp_path / "home" / ".codex")}
    repo = Path(__file__).parents[3]
    installation.install(app="codex", source=repo, home=tmp_path / "home", env=env)
    original_status = installation.status
    monkeypatch.setattr(installation, "status", lambda env: original_status(env=env, home=tmp_path / "home"))

    environment = {"providers": {"codex": {"cli": True, "session": True}}, "pdf_browser": False}
    monkeypatch.setattr(core, "core_info", lambda run=None: {"contract": core.CONTRACT, "version": "0.1.0",
                                                             "environment": environment})
    report = assembly.diagnose()
    assert report["installation"]["installed"] is True
    assert report["installation"]["app"] == "codex"
    assert report["core"]["environment"] == environment
    assert str(tmp_path) not in repr(report)


def test_diagnose_reports_the_saved_setup(harness_env, tmp_path: Path):
    from litman_harness.local_paths import settings_path
    path = settings_path(harness_env)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text('provider = "codex"\nmodel = "gpt-5.6-luna"\n', encoding="utf-8")
    report = assembly.diagnose()
    assert report["setup"] == {"configured": True, "provider": "codex", "model": "gpt-5.6-luna"}


class _Docs:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def get(self, document_id):
        self.calls.append(document_id)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def _with_docs(monkeypatch, docs):
    class Services:
        class expediente:
            @staticmethod
            def identity():
                return {"email": "persona@example.com"}

    services = Services()
    services.docs = docs
    services.sheets = object()  # sheets_api_status() must tolerate this and report "unknown"
    monkeypatch.setattr(assembly, "build_services", lambda env=None: services)


def test_diagnose_reports_the_docs_api_enabled_when_the_probe_is_not_found(unconfigured_env, monkeypatch):
    from litman_harness.adapters.docs import docs_http_error
    docs = _Docs(docs_http_error(404))
    _with_docs(monkeypatch, docs)
    report = assembly.diagnose()
    assert report["docs_api"] == "enabled" and docs.calls == [assembly.DOCS_PROBE_ID]
    assert report["identity"] == {"email": "persona@example.com"}
    assert not any(item["code"] == "not_found" for item in report["errors"])


def test_diagnose_reports_the_docs_api_disabled(unconfigured_env, monkeypatch):
    from litman_harness.adapters.docs import docs_http_error
    content = b'{"error": {"code": 403, "errors": [{"reason": "accessNotConfigured"}]}}'
    _with_docs(monkeypatch, _Docs(docs_http_error(403, content)))
    report = assembly.diagnose()
    assert report["docs_api"] == "disabled"
    assert not any(item["code"] == "docs_api_disabled" for item in report["errors"])


def test_diagnose_reports_the_docs_api_unknown_and_never_fails_because_of_it(unconfigured_env, monkeypatch):
    from litman_harness.adapters.docs import docs_http_error
    from litman_harness.errors import HarnessError
    for outcome in (docs_http_error(401), docs_http_error(500), HarnessError("read_only_adapter", "x"),
                    RuntimeError("offline"), {"revisionId": "r1"}):
        _with_docs(monkeypatch, _Docs(outcome))
        report = assembly.diagnose()
        assert report["docs_api"] == ("enabled" if isinstance(outcome, dict) else "unknown")
        assert report["identity"] == {"email": "persona@example.com"}


def test_diagnose_reports_the_docs_api_unknown_without_services(unconfigured_env, monkeypatch):
    monkeypatch.setattr(assembly, "build_services", lambda env=None: (_ for _ in ()).throw(RuntimeError("offline")))
    assert assembly.diagnose()["docs_api"] == "unknown"


def test_diagnose_reports_the_docs_api_unknown_with_the_metadata_adapter(harness_env):
    assert assembly.diagnose()["docs_api"] == "unknown"


class _Sheets:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def get(self, spreadsheet_id):
        self.calls.append(spreadsheet_id)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def _with_sheets(monkeypatch, sheets):
    class Services:
        class expediente:
            @staticmethod
            def identity():
                return {"email": "persona@example.com"}

    services = Services()
    services.docs = _Docs({})
    services.sheets = sheets
    monkeypatch.setattr(assembly, "build_services", lambda env=None: services)


def test_diagnose_reports_the_sheets_api_enabled_when_the_probe_is_not_found(unconfigured_env, monkeypatch):
    from litman_harness.adapters.sheets import sheets_http_error
    sheets = _Sheets(sheets_http_error(404))
    _with_sheets(monkeypatch, sheets)
    report = assembly.diagnose()
    assert report["sheets_api"] == "enabled" and sheets.calls == [assembly.SHEETS_PROBE_ID]
    assert not any(item["code"] == "not_found" for item in report["errors"])


def test_diagnose_reports_the_sheets_api_disabled(unconfigured_env, monkeypatch):
    from litman_harness.adapters.sheets import sheets_http_error
    content = b'{"error": {"code": 403, "errors": [{"reason": "accessNotConfigured"}]}}'
    _with_sheets(monkeypatch, _Sheets(sheets_http_error(403, content)))
    report = assembly.diagnose()
    assert report["sheets_api"] == "disabled"
    assert not any(item["code"] == "sheets_api_disabled" for item in report["errors"])


def test_diagnose_reports_the_sheets_api_unknown_and_never_fails_because_of_it(unconfigured_env, monkeypatch):
    from litman_harness.adapters.sheets import sheets_http_error
    from litman_harness.errors import HarnessError
    for outcome in (sheets_http_error(401), sheets_http_error(500), HarnessError("read_only_adapter", "x"),
                    RuntimeError("offline"), {"sheets": []}):
        _with_sheets(monkeypatch, _Sheets(outcome))
        report = assembly.diagnose()
        assert report["sheets_api"] == ("enabled" if isinstance(outcome, dict) else "unknown")


def test_diagnose_reports_the_sheets_api_unknown_with_the_metadata_adapter(harness_env):
    assert assembly.diagnose()["sheets_api"] == "unknown"
