from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

# Shared doubles live in tests/fakes.py (tests have no packages).
sys.path.insert(0, str(Path(__file__).parent))

FOLDER = "application/vnd.google-apps.folder"
HARNESS_VARIABLES = ("LITMAN_HARNESS_METADATA", "LITMAN_HARNESS_OAUTH_TOKEN", "LITMAN_HARNESS_OAUTH_CLIENT",
                     "LITMAN_HARNESS_PLAN_STORE", "LITMAN_HARNESS_WORK_DIR")

METADATA = {
    "about": {"user": {"permissionId": "person-1", "emailAddress": "persona@example.test",
                       "displayName": "Persona"}},
    "resources": [
        {"id": "root", "name": "Licitación", "mimeType": FOLDER, "version": "1", "driveId": "shared",
         "capabilities": {"canListChildren": True}},
        {"id": "source", "name": "pliego.pdf", "mimeType": "application/pdf", "version": "4", "size": "123",
         "driveId": "shared", "parents": ["root"], "capabilities": {"canDownload": True},
         "md5Checksum": "0123456789abcdef0123456789abcdef"},
    ],
}


@pytest.fixture
def harness_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Isolated metadata configuration; never the developer's real harness settings."""
    for name in HARNESS_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps(METADATA), encoding="utf-8")
    values = {"LITMAN_HARNESS_METADATA": str(metadata), "LITMAN_HARNESS_PLAN_STORE": str(tmp_path / "plans"),
              "XDG_STATE_HOME": str(tmp_path / "state"), "XDG_CONFIG_HOME": str(tmp_path / "config")}
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


@pytest.fixture
def unconfigured_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in HARNESS_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
