from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from litman_harness.analysis import inputs
from litman_harness.analysis.inputs import download_originals
from litman_harness.dossier.models import FOLDER_MIME, Resource
from litman_harness.errors import HarnessError
from litman_harness.plans.models import Plan, PlanAction


def _plan(*names: str) -> Plan:
    actions = tuple(PlanAction("download_original", f"id{i}", name, None, hashlib.md5(b"ok").hexdigest())
                    for i, name in enumerate(names))
    return Plan("analysis", "root", "person", actions, {f"id{i}": hashlib.md5(b"ok").hexdigest()
                                                             for i in range(len(names))})


class Drive:
    def __init__(self):
        self.root = Resource("root", "root", FOLDER_MIME, "1", drive_id="d", capabilities={"canListChildren": True})
        self.files = {f"id{i}": Resource(f"id{i}", "x.pdf", "application/pdf", "1", 2, "d", ("root",),
                                            capabilities={"canDownload": True}, md5_checksum=hashlib.md5(b"ok").hexdigest())
                      for i in range(5)}
        self.destinations: list[Path] = []

    def get(self, file_id):
        return self.root if file_id == "root" else self.files[file_id]

    def download(self, file_id, destination):
        self.destinations.append(destination)
        destination.write_bytes(b"ok")


def test_windows_safe_names_snapshot_and_classification_clues(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(inputs.platform, "system", lambda: "Windows")
    drive = Drive()
    plan = _plan("PCAP: anuncio/adjudicación .PDF", "CON...docx", "muy largo " + "á" * 400 + ".pdf")
    snapshot = download_originals(drive, drive.root, plan, tmp_path)
    names = [item["local_name"] for item in snapshot]
    assert all("/" not in name and "\\" not in name and not name.endswith((".", " ")) for name in names)
    assert "PCAP_ anuncio" in names[0] and "adjudicación" in names[0]
    assert names[1].startswith("id1-_CON") and len(names[2]) <= inputs.WINDOWS_COMPONENT_LIMIT
    assert all(path.is_file() for path in drive.destinations)
    assert snapshot[0]["name"] == "PCAP: anuncio/adjudicación .PDF"


def test_windows_rejects_deep_workspace_before_downloading(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(inputs.platform, "system", lambda: "Windows")
    drive = Drive()
    with pytest.raises(HarnessError) as raised:
        download_originals(drive, drive.root, _plan("PCAP.pdf"), tmp_path / ("x" * 220))
    assert raised.value.code == "work_path_too_long"
    assert not drive.destinations


def test_windows_rejects_case_insensitive_local_name_collisions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(inputs.platform, "system", lambda: "Windows")
    checksum = hashlib.md5(b"ok").hexdigest()
    plan = Plan("analysis", "root", "person", (
        PlanAction("download_original", "A", "PCAP.pdf", None, checksum),
        PlanAction("download_original", "a", "PCAP.pdf", None, checksum),
    ), {"A": checksum, "a": checksum})
    with pytest.raises(HarnessError) as raised:
        download_originals(Drive(), Drive().root, plan, tmp_path)
    assert raised.value.code == "local_name_collision"
