from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import subprocess
import tomllib

import pytest

from litman_harness.analysis import AnalysisService
from litman_harness.models import HarnessError, Resource


class Drive:
    def __init__(self):
        self.root = Resource("root", "root", "application/vnd.google-apps.folder", "1", drive_id="shared", capabilities={"canListChildren": True})
        self.item = Resource("file", "source.pdf", "application/pdf", "1", 2, "shared", ("root",), capabilities={"canDownload": True})
    def get(self, file_id): return self.root if file_id == "root" else self.item
    def download(self, file_id, destination: Path): destination.write_bytes(b"ok")


def test_analysis_preview_rejects_native_google_documents():
    drive = Drive(); drive.item = replace(drive.item, mime_type="application/vnd.google-apps.document")
    with pytest.raises(HarnessError, match="no se exportan"):
        AnalysisService(drive).preview("root", ["file"], "assessment", "person")


def test_analysis_preview_has_closed_catalog_and_versions():
    plan = AnalysisService(Drive()).preview("root", ["file"], "detailed-analysis", "person")
    assert plan.snapshot == {"root": "1", "file": "1"}
    assert "simulador_economico.xlsx" in plan.actions[-1].metadata["expected_catalog"]


def test_analysis_preview_rejects_original_outside_selected_root():
    drive = Drive(); drive.item = replace(drive.item, parents=("other",))
    with pytest.raises(HarnessError, match="pertenecer"):
        AnalysisService(drive).preview("root", ["file"], "assessment", "person")


def test_analysis_preview_rejects_missing_download_capability():
    drive = Drive(); drive.item = replace(drive.item, capabilities={"canDownload": False})
    with pytest.raises(HarnessError, match="descargar"):
        AnalysisService(drive).preview("root", ["file"], "assessment", "person")


def test_execute_cleans_success_workspace_and_ignores_core_diagnostics(tmp_path: Path):
    drive = Drive(); plan = AnalysisService(drive).preview("root", ["file"], "assessment", "person")
    def run(command, **kwargs):
        config = tomllib.loads(Path(command[-1]).read_text()); output = Path(config["output"]["directory"])
        run_dir = output / "core-run"; (run_dir / "output").mkdir(parents=True)
        (run_dir / "output" / "validation.json").write_text('{"valid": true}')
        (run_dir / "output" / "ficha_oportunidad.pdf").write_bytes(b"pdf")
        (run_dir / "output" / "diagnostic.txt").write_text("private diagnostic")
        return subprocess.CompletedProcess(command, 0, json.dumps({"status": "succeeded", "publication_id": "publication", "local_path": str(run_dir)}), "")
    result = AnalysisService(drive, run=run).execute_local(plan, plan.id, "codex", tmp_path)
    assert result["status"] == "local_validated_pending_publication_gate"
    assert list(tmp_path.iterdir()) == []


def test_execute_retains_failed_private_workspace(tmp_path: Path):
    drive = Drive(); plan = AnalysisService(drive).preview("root", ["file"], "assessment", "person")
    def run(command, **kwargs): return subprocess.CompletedProcess(command, 1, "", "failed")
    with pytest.raises(HarnessError) as raised:
        AnalysisService(drive, run=run).execute_local(plan, plan.id, "codex", tmp_path)
    workspace = Path(raised.value.details["workspace"])
    assert workspace.is_dir() and workspace.parent == tmp_path


def test_execute_rejects_unapproved_provider_before_toml_creation(tmp_path: Path):
    drive = Drive(); plan = AnalysisService(drive).preview("root", ["file"], "assessment", "person")
    with pytest.raises(HarnessError, match="no autorizado"):
        AnalysisService(drive).execute_local(plan, plan.id, "codex\"\n[output]", tmp_path)
    assert list(tmp_path.iterdir()) == []
