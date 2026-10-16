from __future__ import annotations

from pathlib import Path

import pytest
from fakes import AtomicSharedState, core_run, dossier_drive

from litman_harness.analysis.service import AnalysisService
from litman_harness.dossier.manifest import Manifest
from litman_harness.dossier.models import FOLDER_MIME, GOOGLE_DOC_MIME, Resource
from litman_harness.dossier.publication import PublicationService
from litman_harness.dossier.service import ExpedienteService
from litman_harness.dossier.shared_state import UnavailableSharedState
from litman_harness.errors import HarnessError
from litman_harness.plans import PlanStore


class Setup:
    def __init__(self, tmp_path: Path, *, live_offer: bool = False, incorporate: bool = True):
        self.drive = dossier_drive()
        self.store = PlanStore(tmp_path / "plans")
        self.work = tmp_path / "work"
        self.state = AtomicSharedState(self.drive)
        self.dossier = ExpedienteService(self.drive, self.store, self.state)
        self.publication = PublicationService(self.dossier, self.work)
        if incorporate:
            plan = self.dossier.preview_incorporation("root", ["source"],
                                                      live_offer_id="offer-doc" if live_offer else None)
            assert self.dossier.apply_incorporation(plan.id)["status"] == "succeeded"

    def analyse(self, job_type: str) -> dict:
        analysis = AnalysisService(self.drive, self.store, work_root=self.work, run=core_run(job_type),
                                   settings=lambda: {"provider": "codex"})
        return analysis.execute(analysis.preview("root", ["source"], job_type).id)

    def manifest(self) -> Manifest:
        resource = next(item for item in self.drive.resources.values() if item.name == "manifest.json")
        return Manifest.parse(self.drive.contents[resource.id].decode())

    def publish(self, analysis: dict) -> dict:
        plan = self.publication.preview(analysis["operation_id"])
        return self.publication.apply(plan.id)


def test_gate_closed_publication_writes_nothing_and_keeps_workspace(tmp_path: Path):
    setup = Setup(tmp_path)
    analysis = setup.analyse("assessment")
    gated = PublicationService(ExpedienteService(setup.drive, setup.store, UnavailableSharedState()), setup.work)
    created = list(setup.drive.created)
    plan = gated.preview(analysis["operation_id"])
    result = gated.apply(plan.id)
    assert result["status"] == "pending_concurrency_gate" and result["writes"] is False
    assert setup.drive.created == created and Path(analysis["workspace"]).is_dir()


def test_assessment_is_published_by_id_in_a_run_folder_and_cited_in_context(tmp_path: Path):
    setup = Setup(tmp_path)
    analysis = setup.analyse("assessment")
    plan = setup.publication.preview(analysis["operation_id"])
    assert [a.kind for a in plan.actions] == ["create_run_folder", "upload_public_artifact", "set_phase",
                                              "update_context", "update_manifest"]
    result = setup.publication.apply(plan.id)
    manifest = setup.manifest()
    run_folder = setup.drive.resources[result["run_folder_id"]]
    assert run_folder.mime_type == FOLDER_MIME and run_folder.parents == (manifest.folders["initial"],)
    assert run_folder.name == f"{analysis['completed_at'][:10]} pub-1"
    uploaded = setup.drive.resources[result["artifacts"][0]["file_id"]]
    assert uploaded.name == "ficha_oportunidad.pdf" and uploaded.parents == (run_folder.id,)
    entry = manifest.analyses[0]
    assert entry["operation_id"] == analysis["operation_id"] and entry["status"] == "published"
    assert entry["source_originals"][0]["drive_version"] == "4" and manifest.originals[0]["sha256"]
    assert manifest.workflow_phase == "analisis_inicial" and manifest.live_offer is None
    context = setup.drive.contents[manifest.context_file_id].decode()
    assert f"operación `{analysis['operation_id']}`" in context and "publicación `pub-1`" in context
    assert f"[ficha_oportunidad.pdf](https://drive.google.com/open?id={uploaded.id}): ficha de oportunidad" in context
    assert "Todavía no hay resultados" not in context
    assert not Path(analysis["workspace"]).exists()
    assert setup.store.record(setup.drive.user, analysis["operation_id"]).status == "published"
    assert setup.publication.apply(plan.id)["replayed"] is True


def test_first_detailed_analysis_converts_one_live_offer_and_reanalysis_keeps_it(tmp_path: Path):
    setup = Setup(tmp_path)
    first = setup.publish(setup.analyse("detailed-analysis"))
    manifest = setup.manifest()
    offer = setup.drive.resources[manifest.live_offer["document_id"]]
    assert offer.mime_type == GOOGLE_DOC_MIME and offer.parents == (manifest.folders["offer"],)
    assert manifest.live_offer["origin_kind"] == "core_conversion"
    technical = next(a for a in first["artifacts"] if a["role"] == "technical_document")
    assert technical["name"] == "memoria_tecnica.docx"
    assert manifest.live_offer["origin_artifact_id"] == technical["file_id"]
    second_analysis = setup.analyse("detailed-analysis")
    plan = setup.publication.preview(second_analysis["operation_id"])
    assert "convert_live_offer" not in [a.kind for a in plan.actions]
    setup.publication.apply(plan.id)
    manifest = setup.manifest()
    assert len(manifest.analyses) == 2 and manifest.live_offer["document_id"] == offer.id
    assert sum(item.mime_type == GOOGLE_DOC_MIME and manifest.folders["offer"] in item.parents
               for item in setup.drive.resources.values()) == 1


def test_existing_live_offer_is_not_replaced_by_conversion(tmp_path: Path):
    setup = Setup(tmp_path, live_offer=True)
    analysis = setup.analyse("detailed-analysis")
    plan = setup.publication.preview(analysis["operation_id"])
    assert "convert_live_offer" not in [a.kind for a in plan.actions]
    setup.publication.apply(plan.id)
    assert setup.manifest().live_offer["document_id"] == "offer-doc"


def test_partial_failure_resumes_without_duplicate_uploads(tmp_path: Path):
    setup = Setup(tmp_path)
    analysis = setup.analyse("detailed-analysis")
    plan = setup.publication.preview(analysis["operation_id"])
    setup.drive.crash_on_create = {len(setup.drive.created) + 3}
    with pytest.raises(HarnessError) as raised:
        setup.publication.apply(plan.id)
    assert raised.value.code == "operation_interrupted"
    setup.drive.crash_on_create = set()
    result = setup.publication.apply(plan.id)
    assert result["status"] == "succeeded"
    names = [item.name for item in setup.drive.resources.values() if result["run_folder_id"] in item.parents]
    assert sorted(names) == sorted(set(names)) and len(names) == 4


def test_altered_local_artifact_is_rejected(tmp_path: Path):
    setup = Setup(tmp_path)
    analysis = setup.analyse("assessment")
    plan = setup.publication.preview(analysis["operation_id"])
    Path(analysis["public_artifacts"][0]["path"]).write_bytes(b"tampered")
    created = list(setup.drive.created)
    with pytest.raises(HarnessError) as raised:
        setup.publication.apply(plan.id)
    assert raised.value.code == "local_artifact_changed" and setup.drive.created == created
    with pytest.raises(HarnessError):
        setup.publication.preview(analysis["operation_id"])


def test_publication_requires_an_adopted_dossier(tmp_path: Path):
    setup = Setup(tmp_path, incorporate=False)
    analysis = setup.analyse("assessment")
    with pytest.raises(HarnessError) as raised:
        setup.publication.preview(analysis["operation_id"])
    assert raised.value.code == "dossier_not_adopted"
    with pytest.raises(HarnessError) as raised:
        setup.publication.preview("unknown-operation")
    assert raised.value.code == "unknown_operation"


def test_hand_edited_context_does_not_orphan_a_publication(tmp_path: Path):
    setup = Setup(tmp_path)
    context_id = setup.manifest().context_file_id
    setup.drive.write_text(context_id, "# notas propias\n")
    analysis = setup.analyse("assessment")
    result = setup.publish(analysis)
    assert result["status"] == "succeeded" and result["context_conflict"]["reason"] == "edited_outside_litman"
    assert setup.manifest().analyses[0]["operation_id"] == analysis["operation_id"]
    assert setup.drive.contents[context_id] == b"# notas propias\n"


def test_manifest_changed_between_preview_and_apply_is_merged(tmp_path: Path):
    setup = Setup(tmp_path)
    analysis = setup.analyse("assessment")
    plan = setup.publication.preview(analysis["operation_id"])
    setup.drive.add(Resource("annex", "anexo.pdf", "application/pdf", "1", drive_id="shared",
                             parents=("root",)), b"anexo")
    other = setup.dossier.preview_incorporation("root", ["annex"])
    setup.dossier.apply_incorporation(other.id)
    assert setup.publication.apply(plan.id)["status"] == "succeeded"
    manifest = setup.manifest()
    assert [item["file_id"] for item in manifest.originals] == ["source", "annex"]
    assert [item["operation_id"] for item in manifest.analyses] == [analysis["operation_id"]]
    assert [item["kind"] for item in manifest.history] == ["incorporation", "incorporation", "publication"]


def test_concurrent_manifest_write_is_recoverable_without_duplicate_uploads(tmp_path: Path):
    setup = Setup(tmp_path)
    analysis = setup.analyse("assessment")
    plan = setup.publication.preview(analysis["operation_id"])
    setup.state.race_before_update = {"manifest.json"}
    with pytest.raises(HarnessError) as raised:
        setup.publication.apply(plan.id)
    assert raised.value.code == "manifest_changed_retry"
    assert setup.dossier.recover(plan.operation_id)["status"] == "recoverable"
    created = list(setup.drive.created)
    result = setup.publication.apply(plan.id)
    assert result["status"] == "succeeded" and setup.drive.created == created
    assert len([i for i in setup.drive.resources.values() if result["run_folder_id"] in i.parents]) == 1


def test_live_offer_registered_after_preview_skips_the_conversion(tmp_path: Path):
    setup = Setup(tmp_path)
    analysis = setup.analyse("detailed-analysis")
    plan = setup.publication.preview(analysis["operation_id"])
    assert "convert_live_offer" in [a.kind for a in plan.actions]
    offer = setup.dossier.preview_incorporation("root", live_offer_id="offer-doc")
    setup.dossier.apply_incorporation(offer.id)
    result = setup.publication.apply(plan.id)
    manifest = setup.manifest()
    assert result["status"] == "succeeded" and manifest.live_offer["document_id"] == "offer-doc"
    assert not any(item.mime_type == GOOGLE_DOC_MIME and manifest.folders["offer"] in item.parents
                   for item in setup.drive.resources.values())
    assert "memoria_tecnica.docx" in [item["name"] for item in result["artifacts"]]


def test_only_the_closed_public_catalogue_reaches_drive(tmp_path: Path):
    setup = Setup(tmp_path)
    analysis = setup.analyse("detailed-analysis")
    (Path(analysis["local_path"]) / "validation.json").write_text("{}")  # stray local file
    result = setup.publish(analysis)
    uploaded = sorted(item.name for item in setup.drive.resources.values()
                      if result["run_folder_id"] in item.parents)
    assert uploaded == sorted(item["name"] for item in analysis["public_artifacts"])
    assert "validation.json" not in uploaded
