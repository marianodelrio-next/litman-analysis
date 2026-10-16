from __future__ import annotations

from pathlib import Path

from litman_harness.adapters.drive_state import DriveSharedState
from litman_harness.adapters.oauth import DesktopOAuthProvider
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


def test_metadata_assembly_stays_read_only(harness_env):
    services = assembly.build_services()
    assert isinstance(services.shared_state, UnavailableSharedState)
    assert services.expediente.shared_state is services.shared_state


def test_diagnose_reports_the_drive_mechanism_with_usable_oauth(unconfigured_env, monkeypatch):
    class Provider:
        def diagnose(self):
            return {"token_present": True, "valid": True, "token_exposed": False}

    monkeypatch.setattr(assembly, "oauth_provider", lambda env=None: Provider())
    monkeypatch.setattr(assembly, "build_services", lambda env=None: (_ for _ in ()).throw(RuntimeError("offline")))
    report = assembly.diagnose()
    assert report["shared_state"] == {"available": True, "mechanism": "drive_v2_if_match"}


def test_diagnose_reports_setup_and_contract_without_configuration(unconfigured_env):
    report = assembly.diagnose()
    assert report["setup"] == {"configured": False, "provider": None, "model": None}
    assert report["core"] == {"contract": None, "version": None, "compatible": False}
    assert "settings.toml" not in repr(report)


def test_diagnose_reports_the_saved_setup(harness_env, tmp_path: Path):
    from litman_harness.local_paths import settings_path
    path = settings_path(harness_env)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text('provider = "codex"\nmodel = "gpt-5.6-luna"\n', encoding="utf-8")
    report = assembly.diagnose()
    assert report["setup"] == {"configured": True, "provider": "codex", "model": "gpt-5.6-luna"}
