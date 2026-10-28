from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import subprocess

import pytest
from fakes import PDF, AtomicSharedState, core_run, dossier_drive

from litman_harness.analysis import service as service_module
from litman_harness.analysis.service import AnalysisService, remove_workspace
from litman_harness.dossier.models import FOLDER_MIME, Resource
from litman_harness.dossier.service import ExpedienteService
from litman_harness.errors import HarnessError
from litman_harness.plans import PlanStore


OK_MD5 = hashlib.md5(b"ok").hexdigest()


class Drive:
    def __init__(self):
        self.root = Resource("root", "root", FOLDER_MIME, "1", drive_id="shared",
                             capabilities={"canListChildren": True})
        self.item = Resource("file", "source.pdf", "application/pdf", "1", 2, "shared", ("root",),
                             capabilities={"canDownload": True}, md5_checksum=OK_MD5)

    def get(self, file_id):
        return self.root if file_id == "root" else self.item

    def about(self):
        return {"user": {"permissionId": "person"}}

    def download(self, file_id, destination: Path):
        destination.write_bytes(b"ok")


def _settings(provider: str = "codex", model: str | None = None):
    def get():
        return {"provider": provider, **({"model": model} if model is not None else {})}
    return get


def service(drive, tmp_path: Path, run=None, *, settings=None, dossier=None) -> AnalysisService:
    kwargs = {"run": run} if run else {}
    return AnalysisService(drive, PlanStore(tmp_path / "plans"), work_root=tmp_path / "work",
                           settings=settings or _settings(), dossier=dossier, **kwargs)


def test_analysis_preview_rejects_native_google_documents():
    drive = Drive()
    drive.item = replace(drive.item, mime_type="application/vnd.google-apps.document")
    with pytest.raises(HarnessError, match="no se exportan"):
        AnalysisService(drive, settings=_settings()).preview("root", ["file"], "assessment")


def test_analysis_preview_requires_setup():
    with pytest.raises(HarnessError) as raised:
        AnalysisService(Drive()).preview("root", ["file"], "assessment")
    assert raised.value.code == "setup_required"
    assert raised.value.details["recommended_action"]["tool"] == "setup"


def test_analysis_preview_has_closed_catalog_versions_and_provider():
    plan = AnalysisService(Drive(), settings=_settings("claude-code")).preview("root", ["file"], "detailed-analysis")
    assert plan.snapshot == {"file": OK_MD5}
    assert plan.account_id == "person"
    run_core = plan.actions[-1].metadata
    assert "economic_simulator" in run_core["expected_roles"]
    assert run_core["provider"] == "claude-code" and run_core["includes_technical_document"] is True


def test_analysis_preview_rejects_original_outside_selected_root():
    drive = Drive()
    drive.item = replace(drive.item, parents=("other",))
    with pytest.raises(HarnessError, match="pertenecer"):
        AnalysisService(drive, settings=_settings()).preview("root", ["file"], "assessment")


def test_analysis_preview_accepts_original_in_expediente_subfolder():
    drive = Drive()
    folder = Resource("folder", "Originales", FOLDER_MIME, "1", drive_id="shared", parents=("root",))
    drive.item = replace(drive.item, parents=("folder",))
    original_get = drive.get
    drive.get = lambda file_id: folder if file_id == "folder" else original_get(file_id)
    assert AnalysisService(drive, settings=_settings()).preview("root", ["file"], "assessment").snapshot["file"] == OK_MD5


def test_analysis_preview_rejects_missing_download_capability():
    drive = Drive()
    drive.item = replace(drive.item, capabilities={"canDownload": False})
    with pytest.raises(HarnessError, match="descargar"):
        AnalysisService(drive, settings=_settings()).preview("root", ["file"], "assessment")


def test_preview_rejects_unapproved_provider_without_storing_a_plan(tmp_path: Path):
    with pytest.raises(HarnessError) as raised:
        service(Drive(), tmp_path, settings=_settings("codex\"\n[output]")).preview("root", ["file"], "assessment")
    assert raised.value.code == "invalid_provider"
    assert not (tmp_path / "plans").exists()


def test_execute_retains_success_workspace_with_flat_public_artifacts(tmp_path: Path):
    drive = Drive()
    analysis = service(drive, tmp_path, core_run())
    plan = analysis.preview("root", ["file"], "assessment")
    result = analysis.execute(plan.id)
    assert result["status"] == "local_validated"
    workspace = Path(result["workspace"])
    assert workspace.is_dir() and workspace.parent == tmp_path / "work"
    assert workspace.stat().st_mode & 0o777 == 0o700
    assert Path(result["local_path"]).is_relative_to(workspace)
    assert [item["name"] for item in result["public_artifacts"]] == ["ficha_oportunidad.pdf"]
    assert result["provider"] == "codex"
    assert result["input_snapshot"][0]["file_id"] == "file"
    assert result["input_snapshot"][0]["local_name"] == "file-source.pdf"


def test_execute_detailed_catalog_includes_the_single_technical_docx(tmp_path: Path):
    analysis = service(Drive(), tmp_path, core_run("detailed-analysis"))
    plan = analysis.preview("root", ["file"], "detailed-analysis")
    result = analysis.execute(plan.id)
    names = [item["name"] for item in result["public_artifacts"]]
    assert names == ["resumen_tecnico.docx", "guia_preparacion_oferta.docx", "propuesta_tecnica.docx",
                     "simulador_economico.xlsx"]
    assert all(Path(item["path"]).is_file() and len(item["sha256"]) == 64 for item in result["public_artifacts"])
    assert result["public_artifacts"][2]["role"] == "technical_document"
    run_dir = Path(result["local_path"])
    assert sorted(path.name for path in run_dir.iterdir()) == sorted(names)  # no internal Core file exists


def test_execute_retains_failed_private_workspace(tmp_path: Path):
    import json as _json
    def run(command, **kwargs):
        if command[-1] == "info":
            return subprocess.CompletedProcess(command, 0, _json.dumps(
                {"contract": 1, "version": "0.1.0", "providers": ["claude-code", "codex"]}), "")
        payload = {"contract": 1, "status": "failed", "error": {"code": "analysis_failed", "message": "fallo"}}
        return subprocess.CompletedProcess(command, 1, _json.dumps(payload), "failed")
    analysis = service(Drive(), tmp_path, run)
    plan = analysis.preview("root", ["file"], "assessment")
    with pytest.raises(HarnessError) as raised:
        analysis.execute(plan.id)
    assert raised.value.code == "core_failed"
    workspace = Path(raised.value.details["workspace"])
    assert workspace.is_dir() and workspace.parent == tmp_path / "work"


def test_execute_rejects_original_changed_during_download(tmp_path: Path):
    drive = Drive()
    analysis = service(drive, tmp_path, core_run())
    plan = analysis.preview("root", ["file"], "assessment")

    def download(file_id, destination):
        destination.write_bytes(b"ok")
        drive.item = replace(drive.item, md5_checksum="0" * 32)

    drive.download = download
    with pytest.raises(HarnessError, match="durante la descarga") as raised:
        analysis.execute(plan.id)
    assert raised.value.code == "stale_plan"


def test_execute_requires_stored_plan_of_active_account(tmp_path: Path):
    drive = Drive()
    analysis = service(drive, tmp_path, core_run())
    plan = analysis.preview("root", ["file"], "assessment")
    drive.about = lambda: {"user": {"permissionId": "other"}}
    with pytest.raises(HarnessError) as raised:
        analysis.execute(plan.id)
    assert raised.value.code == "unknown_plan"
    assert not (tmp_path / "work").exists()


def test_execute_rejects_core_run_outside_private_output(tmp_path: Path):
    outside = tmp_path / "elsewhere"
    analysis = service(Drive(), tmp_path, core_run(local_path=outside))
    plan = analysis.preview("root", ["file"], "assessment")
    with pytest.raises(HarnessError) as raised:
        analysis.execute(plan.id)
    assert raised.value.code == "invalid_core_result" and "fuera del workspace" in str(raised.value)


def test_execute_registers_validated_result_and_replays(tmp_path: Path):
    calls = []
    run = core_run()

    def counted(command, **kwargs):
        calls.append(command)
        return run(command, **kwargs)

    store = PlanStore(tmp_path / "plans")
    analysis = AnalysisService(Drive(), store, work_root=tmp_path / "work", run=counted, settings=_settings())
    plan = analysis.preview("root", ["file"], "assessment")
    result = analysis.execute(plan.id)
    record = store.record("person", plan.operation_id)
    assert record.kind == "analysis" and record.result == {k: v for k, v in result.items() if k != "operation_status"}
    assert "summary" not in result
    assert result["core_version"] == "0.1.0" and result["input_snapshot"][0]["drive_version"] == "1"
    assert result["input_snapshot"][0]["md5_checksum"] == OK_MD5
    runs = len(calls)
    assert analysis.execute(plan.id)["publication_id"] == "pub-1" and len(calls) == runs


def test_discard_removes_only_the_local_workspace(tmp_path: Path):
    analysis = service(Drive(), tmp_path, core_run())
    plan = analysis.preview("root", ["file"], "assessment")
    workspace = Path(analysis.execute(plan.id)["workspace"])
    result = analysis.discard(plan.operation_id)
    assert result["status"] == "discarded" and not workspace.exists() and (tmp_path / "work").is_dir()
    with pytest.raises(HarnessError) as raised:
        analysis.discard(plan.operation_id)
    assert raised.value.code == "invalid_operation_state"


def test_windows_workspace_cleanup_uses_readonly_retry_and_rejects_external_path(tmp_path: Path,
                                                                                   monkeypatch: pytest.MonkeyPatch):
    root, workspace = tmp_path / "work", tmp_path / "work" / "run"
    workspace.mkdir(parents=True)
    monkeypatch.setattr(service_module.platform, "system", lambda: "Windows")
    calls = []

    def rmtree(path, **kwargs):
        calls.append((path, kwargs))

    monkeypatch.setattr(service_module.shutil, "rmtree", rmtree)
    remove_workspace(root, workspace)
    assert calls == [(workspace.resolve(), {"onerror": service_module._remove_readonly})]
    with pytest.raises(HarnessError) as raised:
        remove_workspace(root, tmp_path / "outside")
    assert raised.value.code == "unsafe_workspace"


def test_execute_rejects_original_changed_after_preview(tmp_path: Path):
    drive = Drive()
    analysis = service(drive, tmp_path, core_run())
    plan = analysis.preview("root", ["file"], "assessment")
    drive.item = replace(drive.item, md5_checksum="0" * 32)
    with pytest.raises(HarnessError, match="antes de ejecutar") as raised:
        analysis.execute(plan.id)
    assert raised.value.code == "stale_plan" and not (tmp_path / "work").exists()


def _unknown_role(run_dir, payload):
    (run_dir / "extra.pdf").write_bytes(b"x")
    payload["artifacts"].append({"role": "not_a_real_role", "name": "extra.pdf",
                                 "checksum": hashlib.sha256(b"x").hexdigest()})


def _missing_role(run_dir, payload):
    payload["artifacts"] = [item for item in payload["artifacts"] if item["role"] != "economic_simulator"]


def _checksum(run_dir, payload):
    (run_dir / "resumen_tecnico.docx").write_bytes(b"otro contenido")


def _duplicate_role(run_dir, payload):
    (run_dir / "otro.docx").write_bytes(b"y")
    payload["artifacts"].append({"role": "technical_document", "name": "otro.docx",
                                 "checksum": hashlib.sha256(b"y").hexdigest()})


def _no_artifacts(run_dir, payload):
    del payload["artifacts"]


def _undeclared_file(run_dir, payload):
    (run_dir / "simulador_economico.xlsx").unlink()


@pytest.mark.parametrize(("tamper", "message"), (
    (_unknown_role, "rol de artefacto desconocido"), (_missing_role, "Faltan roles obligatorios"),
    (_checksum, "SHA-256"), (_duplicate_role, "mismo rol más de una vez"),
    (_no_artifacts, "publicación validada"), (_undeclared_file, "Falta un artefacto"),
))
def test_execute_rejects_results_outside_the_public_contract(tmp_path: Path, tamper, message):
    analysis = service(Drive(), tmp_path, core_run("detailed-analysis", tamper=tamper))
    plan = analysis.preview("root", ["file"], "detailed-analysis")
    with pytest.raises(HarnessError, match=message) as raised:
        analysis.execute(plan.id)
    assert raised.value.code == "invalid_core_result"


def test_root_version_change_does_not_invalidate_the_plan(tmp_path: Path):
    drive = Drive()
    analysis = service(drive, tmp_path, core_run())
    plan = analysis.preview("root", ["file"], "assessment")
    assert plan.snapshot == {"file": OK_MD5}
    drive.root = replace(drive.root, version="9")
    drive.item = replace(drive.item, version="7")  # same content, new Drive version
    assert analysis.execute(plan.id)["status"] == "local_validated"


def test_downloaded_bytes_must_match_the_planned_md5(tmp_path: Path):
    drive = Drive()
    analysis = service(drive, tmp_path, core_run())
    plan = analysis.preview("root", ["file"], "assessment")
    drive.download = lambda file_id, destination: destination.write_bytes(b"different")
    with pytest.raises(HarnessError, match="durante la descarga") as raised:
        analysis.execute(plan.id)
    assert raised.value.code == "stale_plan"


def test_original_without_md5_is_rejected_in_preview():
    drive = Drive()
    drive.item = replace(drive.item, md5_checksum=None)
    with pytest.raises(HarnessError) as raised:
        AnalysisService(drive, settings=_settings()).preview("root", ["file"], "assessment")
    assert raised.value.code == "missing_checksum"


def _adopted_dossier(tmp_path: Path):
    """An adopted dossier with ``source`` registered as its only active original."""
    drive = dossier_drive()
    dossier = ExpedienteService(drive, PlanStore(tmp_path / "dossier-plans"), AtomicSharedState(drive))
    dossier.apply_incorporation(dossier.preview_incorporation("root", ["source"]).id)
    return drive, dossier


def test_preview_rejects_a_registered_original_whose_content_drifted(tmp_path: Path):
    drive, dossier = _adopted_dossier(tmp_path)
    drive.resources["source"] = replace(drive.resources["source"], md5_checksum="0" * 32)
    analysis = service(drive, tmp_path, settings=_settings(), dossier=dossier)
    with pytest.raises(HarnessError, match="cambió desde que se registró") as raised:
        analysis.preview("root", ["source"], "assessment")
    assert raised.value.code == "registered_original_changed"
    assert raised.value.details["file_id"] == "source"


def test_preview_rejects_a_registered_original_with_no_stored_checksum(tmp_path: Path):
    """Same drift comparison as ``status``: a missing registered MD5 against a present one is drift too."""
    drive, dossier = _adopted_dossier(tmp_path)
    state = dossier.load_state(drive.resources["root"])
    state.manifest.originals[0]["md5_checksum"] = None
    drive.contents[state.manifest_file.id] = state.manifest.serialize().encode()
    analysis = service(drive, tmp_path, settings=_settings(), dossier=dossier)
    with pytest.raises(HarnessError) as raised:
        analysis.preview("root", ["source"], "assessment")
    assert raised.value.code == "registered_original_changed"


def test_preview_marks_registered_and_unregistered_selections(tmp_path: Path):
    drive, dossier = _adopted_dossier(tmp_path)
    drive.add(Resource("extra", "nuevo.pdf", PDF, "1", drive_id="shared", parents=("root",),
                       capabilities={"canDownload": True}), b"nuevo")
    analysis = service(drive, tmp_path, settings=_settings(), dossier=dossier)
    plan = analysis.preview("root", ["source", "extra"], "assessment")
    flags = {action.resource_id: action.metadata["registered"] for action in plan.actions
             if action.kind == "download_original"}
    assert flags == {"source": True, "extra": False}


def test_preview_without_a_dossier_never_treats_a_selection_as_registered(tmp_path: Path):
    drive = Drive()
    analysis = service(drive, tmp_path, settings=_settings())
    plan = analysis.preview("root", ["file"], "assessment")
    assert plan.actions[0].metadata["registered"] is False
