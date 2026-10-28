from __future__ import annotations

from dataclasses import replace
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
from litman_harness.plans.models import Plan, PlanAction


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


def test_assessment_is_published_flat_in_the_phase_folder_and_cited_in_context(tmp_path: Path):
    setup = Setup(tmp_path)
    analysis = setup.analyse("assessment")
    plan = setup.publication.preview(analysis["operation_id"])
    assert [a.kind for a in plan.actions] == ["upload_public_artifact", "set_phase", "update_context",
                                              "update_manifest"]
    folders = [item.id for item in setup.drive.resources.values() if item.mime_type == FOLDER_MIME]
    result = setup.publication.apply(plan.id)
    manifest = setup.manifest()
    assert [item.id for item in setup.drive.resources.values() if item.mime_type == FOLDER_MIME] == folders
    assert result["folder_id"] == manifest.folders["initial"] and "run_folder_id" not in result
    uploaded = setup.drive.resources[result["artifacts"][0]["file_id"]]
    assert uploaded.name == "ficha_oportunidad.pdf" and uploaded.parents == (manifest.folders["initial"],)
    entry = manifest.analyses[0]
    assert entry["operation_id"] == analysis["operation_id"] and entry["status"] == "published"
    assert entry["folder_id"] == manifest.folders["initial"]
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
    assert technical["name"] == "propuesta_tecnica.docx"
    assert manifest.live_offer["origin_artifact_id"] == technical["file_id"]
    second_analysis = setup.analyse("detailed-analysis")
    plan = setup.publication.preview(second_analysis["operation_id"])
    assert "convert_live_offer" not in [a.kind for a in plan.actions]
    original_content = setup.drive.contents[technical["file_id"]]
    second = setup.publication.apply(plan.id)
    repeated = next(a for a in second["artifacts"] if a["role"] == "technical_document")
    assert repeated["name"] == f"propuesta_tecnica ({second_analysis['completed_at'][:10]}).docx"
    assert repeated["file_id"] != technical["file_id"]
    assert setup.drive.resources[technical["file_id"]].name == "propuesta_tecnica.docx"
    assert setup.drive.contents[technical["file_id"]] == original_content
    manifest = setup.manifest()
    assert len(manifest.analyses) == 2 and manifest.live_offer["document_id"] == offer.id
    assert sum(item.mime_type == GOOGLE_DOC_MIME and manifest.folders["offer"] in item.parents
               for item in setup.drive.resources.values()) == 1



def test_renamed_live_offer_remains_registered(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.publish(setup.analyse("detailed-analysis"))
    manifest = setup.manifest()
    offer_id = manifest.live_offer["document_id"]
    assert setup.drive.resources[offer_id].name == "propuesta_tecnica"
    setup.drive.rename(offer_id, "Oferta revisada")
    assert setup.dossier.status("root")["state"] == "adopted"
    analysis = setup.analyse("detailed-analysis")
    plan = setup.publication.preview(analysis["operation_id"])
    assert "convert_live_offer" not in [action.kind for action in plan.actions]
    setup.publication.apply(plan.id)
    manifest = setup.manifest()
    assert manifest.live_offer["document_id"] == offer_id
    assert setup.drive.resources[offer_id].name == "Oferta revisada"
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
    names = [item.name for item in setup.drive.resources.values() if result["folder_id"] in item.parents]
    assert sorted(names) == sorted(set(names)) and len(names) == 4
    assert result["folder_id"] == setup.manifest().folders["detailed"]


def test_repeated_analysis_gets_date_suffixed_names_and_overwrites_nothing(tmp_path: Path):
    setup = Setup(tmp_path)
    first = setup.publish(setup.analyse("assessment"))
    original = first["artifacts"][0]
    content = setup.drive.contents[original["file_id"]]
    analyses = [setup.analyse("assessment"), setup.analyse("assessment")]
    plans = [setup.publication.preview(analyses[0]["operation_id"])]
    assert plans[0].actions[0].name == f"ficha_oportunidad ({analyses[0]['completed_at'][:10]}).pdf"
    assert plans[0].actions[0].metadata["artifact"] == "ficha_oportunidad.pdf"
    second = setup.publication.apply(plans[0].id)
    third = setup.publish(analyses[1])
    day = analyses[1]["completed_at"][:10]
    assert third["artifacts"][0]["name"] == f"ficha_oportunidad ({day}-2).pdf"
    initial = setup.manifest().folders["initial"]
    names = sorted(item.name for item in setup.drive.resources.values() if initial in item.parents)
    assert names == sorted(["ficha_oportunidad.pdf", second["artifacts"][0]["name"],
                            f"ficha_oportunidad ({day}-2).pdf"])
    assert setup.drive.contents[original["file_id"]] == content
    assert [item["folder_id"] for item in setup.manifest().analyses] == [initial] * 3
    assert len({item["artifacts"][0]["file_id"] for item in setup.manifest().analyses}) == 3


def test_publication_plan_stored_before_flat_layout_still_resumes(tmp_path: Path):
    setup = Setup(tmp_path)
    analysis = setup.analyse("assessment")
    current = setup.publication.preview(analysis["operation_id"])
    initial = setup.manifest().folders["initial"]
    folder = PlanAction("create_run_folder", None, f"{analysis['completed_at'][:10]} pub-1", initial,
                        metadata={"role": "run_folder"})
    uploads = [replace(action, parent_id=None, metadata={k: v for k, v in action.metadata.items() if k != "artifact"})
               for action in current.actions if action.kind == "upload_public_artifact"]
    rest = [action for action in current.actions if action.kind != "upload_public_artifact"]
    legacy = Plan("publication", current.root_folder_id, current.account_id, (folder, *uploads, *rest), {})
    setup.store.save(legacy)
    setup.drive.crash_on_create = {len(setup.drive.created) + 1}
    with pytest.raises(HarnessError) as raised:
        setup.publication.apply(legacy.id)
    assert raised.value.code == "operation_interrupted"
    setup.drive.crash_on_create = set()
    result = setup.publication.apply(legacy.id)
    run_folder = setup.drive.resources[result["folder_id"]]
    assert run_folder.mime_type == FOLDER_MIME and run_folder.parents == (initial,)
    assert [item.name for item in setup.drive.resources.values() if run_folder.id in item.parents] == [
        "ficha_oportunidad.pdf"]
    assert setup.manifest().analyses[0]["folder_id"] == run_folder.id


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
    assert len([i for i in setup.drive.resources.values() if result["folder_id"] in i.parents]) == 1


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
    assert "propuesta_tecnica.docx" in [item["name"] for item in result["artifacts"]]


def test_only_the_closed_public_catalogue_reaches_drive(tmp_path: Path):
    setup = Setup(tmp_path)
    analysis = setup.analyse("detailed-analysis")
    (Path(analysis["local_path"]) / "validation.json").write_text("{}")  # stray local file
    result = setup.publish(analysis)
    uploaded = sorted(item.name for item in setup.drive.resources.values()
                      if result["folder_id"] in item.parents)
    assert uploaded == sorted(item["name"] for item in analysis["public_artifacts"])
    assert "validation.json" not in uploaded


def test_publication_backfills_the_sha256_of_an_original_copied_after_the_analysis(tmp_path: Path):
    setup = Setup(tmp_path)
    analysis = setup.analyse("assessment")  # Core read the source ID
    resource = next(item for item in setup.drive.resources.values() if item.name == "manifest.json")
    manifest = setup.manifest()
    manifest.originals[0].pop("placement")
    setup.drive.write_text(resource.id, manifest.serialize())
    setup.drive.add(replace(setup.drive.resources["source"], capabilities={"canDownload": True, "canCopy": True}))
    setup.dossier.apply_incorporation(setup.dossier.preview_incorporation("root").id)
    assert setup.manifest().originals[0]["copied_from"] == "source"
    setup.publish(analysis)
    original = setup.manifest().originals[0]
    assert original["file_id"] != "source" and original["sha256"]
    assert setup.manifest().analyses[0]["source_originals"][0]["file_id"] == "source"


def test_phase_folder_changed_after_preview_blocks_the_uploads(tmp_path: Path):
    setup = Setup(tmp_path)
    analysis = setup.analyse("assessment")
    plan = setup.publication.preview(analysis["operation_id"])
    resource = next(item for item in setup.drive.resources.values() if item.name == "manifest.json")
    manifest = setup.manifest()
    setup.drive.add(Resource("other-initial", "Analisis inicial", FOLDER_MIME, "1", drive_id="shared",
                             parents=("root",)))
    manifest.folders["initial"] = "other-initial"
    setup.drive.write_text(resource.id, manifest.serialize())
    created = list(setup.drive.created)
    result = setup.publication.apply(plan.id)
    assert result["status"] == "conflict" and setup.drive.created == created
