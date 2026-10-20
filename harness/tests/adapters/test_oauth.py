from __future__ import annotations

import json
from pathlib import Path

import pytest

from litman_harness.adapters.oauth import DesktopOAuthProvider
from litman_harness.errors import HarnessError
from litman_harness.local_paths import checkout_root


class Credentials:
    def __init__(self, *, valid=True, expired=False, refresh_token="refresh-secret", token="access-secret"):
        self.valid, self.expired, self.refresh_token, self.token = valid, expired, refresh_token, token
        self.scopes = ["https://www.googleapis.com/auth/drive"]
        self.refreshed = False

    def refresh(self, request):
        self.valid, self.expired, self.refreshed, self.token = True, False, True, "new-access-secret"

    def to_json(self):
        return json.dumps({"token": self.token, "refresh_token": self.refresh_token})


def test_checkout_is_detected_from_package_not_cwd():
    root = checkout_root()
    assert root is not None and (root / ".git").exists()
    assert (root / "harness" / "src" / "litman_harness").is_dir()


def test_token_or_client_inside_checkout_is_rejected(tmp_path: Path):
    with pytest.raises(HarnessError) as raised:
        DesktopOAuthProvider(checkout_root() / "token.json")
    assert raised.value.code == "unsafe_token_path"
    with pytest.raises(HarnessError) as raised:
        DesktopOAuthProvider(tmp_path / "token.json", checkout_root() / "client_secret.json")
    assert raised.value.code == "unsafe_client_path"


def test_token_outside_checkout_is_accepted_even_below_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    provider = DesktopOAuthProvider(tmp_path / "token.json")
    with pytest.raises(HarnessError) as raised:
        provider.drive_service()
    assert raised.value.code == "oauth_login_required"


def test_expired_token_is_refreshed_and_persisted_privately(tmp_path: Path):
    token = tmp_path / "config" / "token.json"
    token.parent.mkdir()
    token.write_text("{}")
    credentials = Credentials(valid=False, expired=True)
    provider = DesktopOAuthProvider(token, loader=lambda path: credentials,
                                    request_factory=lambda: "request", service_factory=lambda creds: creds)
    assert provider.drive_service() is credentials and credentials.refreshed
    assert json.loads(token.read_text())["token"] == "new-access-secret"
    assert token.stat().st_mode & 0o777 == 0o600


def test_invalid_token_without_refresh_requires_login(tmp_path: Path):
    token = tmp_path / "token.json"
    token.write_text("{}")
    provider = DesktopOAuthProvider(token, loader=lambda path: Credentials(valid=False, refresh_token=None))
    with pytest.raises(HarnessError) as raised:
        provider.drive_service()
    assert raised.value.code == "oauth_login_required"


def test_login_uses_installed_app_flow_and_stores_token_0600(tmp_path: Path):
    client = tmp_path / "client_secret.json"
    client.write_text("{}")
    calls = []

    class Flow:
        def run_local_server(self, port):
            calls.append(port)
            return Credentials()

    def flow_factory(path, scopes):
        calls.append((path, scopes))
        return Flow()

    token = tmp_path / "private" / "token.json"
    result = DesktopOAuthProvider(token, client, flow_factory=flow_factory).login()
    assert result["logged_in"] is True and "secret" not in json.dumps(result)
    assert calls == [(client.resolve(), ["https://www.googleapis.com/auth/drive"]), 0]
    assert token.stat().st_mode & 0o777 == 0o600 and token.parent.stat().st_mode & 0o777 == 0o700


def test_login_requires_local_client_file(tmp_path: Path):
    with pytest.raises(HarnessError) as raised:
        DesktopOAuthProvider(tmp_path / "token.json", tmp_path / "missing.json").login()
    assert raised.value.code == "oauth_client_missing"


def test_diagnose_never_exposes_credentials(tmp_path: Path):
    report = DesktopOAuthProvider(tmp_path / "token.json", credentials=Credentials()).diagnose()
    assert report["scopes"] == ["https://www.googleapis.com/auth/drive"] and report["valid"] is True
    assert "secret" not in repr(report)
    missing = DesktopOAuthProvider(tmp_path / "absent.json").diagnose()
    assert missing["token_present"] is False and missing["error"]["code"] == "oauth_login_required"


def test_token_granted_with_an_older_scope_requires_new_login(tmp_path: Path):
    token = tmp_path / "token.json"
    token.write_text("{}")
    old = Credentials()
    old.scopes = ["https://www.googleapis.com/auth/drive.file"]
    provider = DesktopOAuthProvider(token, loader=lambda path: old)
    with pytest.raises(HarnessError) as raised:
        provider.drive_service()
    assert raised.value.code == "oauth_scope_missing"
    assert raised.value.details["granted_scopes"] == ["https://www.googleapis.com/auth/drive.file"]


def test_real_loader_keeps_the_scopes_granted_in_the_token_file(tmp_path: Path):
    from litman_harness.adapters.oauth import _load_credentials
    token = tmp_path / "token.json"
    token.write_text(json.dumps({"token": "t", "refresh_token": "r", "client_id": "c", "client_secret": "s",
                                 "scopes": ["https://www.googleapis.com/auth/drive.file"]}))
    assert _load_credentials(token).scopes == ["https://www.googleapis.com/auth/drive.file"]


def test_docs_service_uses_the_same_drive_scope_credentials(tmp_path: Path):
    from google.oauth2.credentials import Credentials as GoogleCredentials
    credentials = GoogleCredentials(token="access-secret", scopes=["https://www.googleapis.com/auth/drive"])
    provider = DesktopOAuthProvider(tmp_path / "token.json", credentials=credentials)
    service = provider.docs_service()
    assert service._baseUrl.startswith("https://docs.googleapis.com/") and hasattr(service, "documents")
    injected = DesktopOAuthProvider(tmp_path / "token.json", credentials=credentials,
                                    service_factory=lambda creds: ("service", creds))
    assert injected.docs_service() == ("service", credentials)


def test_sheets_service_uses_the_same_drive_scope_credentials(tmp_path: Path):
    from google.oauth2.credentials import Credentials as GoogleCredentials
    credentials = GoogleCredentials(token="access-secret", scopes=["https://www.googleapis.com/auth/drive"])
    provider = DesktopOAuthProvider(tmp_path / "token.json", credentials=credentials)
    service = provider.sheets_service()
    assert service._baseUrl.startswith("https://sheets.googleapis.com/") and hasattr(service, "spreadsheets")
    injected = DesktopOAuthProvider(tmp_path / "token.json", credentials=credentials,
                                    service_factory=lambda creds: ("service", creds))
    assert injected.sheets_service() == ("service", credentials)
