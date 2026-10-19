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


DRIVE_ID = "1" + "A" * 32


def _default_depth_inputs(tmp_path: Path) -> Path:
    inputs_dir = tmp_path / ("x" * (120 - len(str(tmp_path)) - 1))
    assert len(str(inputs_dir)) == 120
    inputs_dir.mkdir()
    return inputs_dir


def _single_original(name: str, file_id: str = DRIVE_ID) -> tuple[Drive, Plan]:
    checksum = hashlib.md5(b"ok").hexdigest()
    drive = Drive()
    drive.files[file_id] = Resource(file_id, name, "application/pdf", "1", 2, "d", ("root",),
                                    capabilities={"canDownload": True}, md5_checksum=checksum)
    plan = Plan("analysis", "root", "person", (PlanAction("download_original", file_id, name, None, checksum),),
                {file_id: checksum})
    return drive, plan


def test_windows_shortens_long_names_to_the_input_path_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(inputs.platform, "system", lambda: "Windows")
    inputs_dir = _default_depth_inputs(tmp_path)
    name = "Pliego de prescripciones técnicas " + "n" * 166 + ".pdf"
    drive, plan = _single_original(name)
    [item] = download_originals(drive, drive.root, plan, inputs_dir)
    local_name = item["local_name"]
    assert local_name.startswith(f"{DRIVE_ID}-") and local_name.endswith(".pdf")
    assert not inputs.WINDOWS_INVALID.search(local_name) and not local_name.endswith((".", " "))
    [target] = drive.destinations
    assert target.is_file() and target.name == local_name
    assert len(str(target)) + inputs.CORE_PATH_MARGIN <= inputs.WINDOWS_PATH_LIMIT
    assert item["name"] == name


def test_windows_long_suffix_is_part_of_the_stem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(inputs.platform, "system", lambda: "Windows")
    inputs_dir = _default_depth_inputs(tmp_path)
    name = "informe.final-version-revisada-definitiva-" + "v" * 80
    drive, plan = _single_original(name)
    [item] = download_originals(drive, drive.root, plan, inputs_dir)
    budget = inputs.WINDOWS_PATH_LIMIT - inputs.CORE_PATH_MARGIN - len(str(inputs_dir)) - 1
    assert item["local_name"] == f"{DRIVE_ID}-{name}"[:budget]


def test_windows_rejects_collisions_after_shortening(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(inputs.platform, "system", lambda: "Windows")
    inputs_dir = _default_depth_inputs(tmp_path)
    checksum = hashlib.md5(b"ok").hexdigest()
    prefix = "Anexo " + "a" * 120
    plan = Plan("analysis", "root", "person", (
        PlanAction("download_original", DRIVE_ID, f"{prefix} uno.pdf", None, checksum),
        PlanAction("download_original", DRIVE_ID.lower(), f"{prefix} dos.pdf", None, checksum),
    ), {DRIVE_ID: checksum, DRIVE_ID.lower(): checksum})
    drive = Drive()
    with pytest.raises(HarnessError) as raised:
        download_originals(drive, drive.root, plan, inputs_dir)
    assert raised.value.code == "local_name_collision"
    assert not drive.destinations


def test_posix_local_names_are_not_shortened(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(inputs.platform, "system", lambda: "Linux")
    inputs_dir = _default_depth_inputs(tmp_path)
    name = "n" * 200 + ".pdf"
    drive, plan = _single_original(name)
    [item] = download_originals(drive, drive.root, plan, inputs_dir)
    assert item["local_name"] == f"{DRIVE_ID}-{name}"
