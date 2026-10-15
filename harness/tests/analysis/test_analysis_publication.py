from __future__ import annotations

from pathlib import Path

import pytest
from fakes import AtomicSharedState, core_run, dossier_drive

from litman_harness.analysis.service import AnalysisService
from litman_harness.dossier.manifest import Manifest
from litman_harness.dossier.models import GOOGLE_DOC_MIME
from litman_harness.dossier.publication import PublicationService
from litman_harness.dossier.service import ExpedienteService
from litman_harness.dossier.shared_state import UnavailableSharedState
from litman_harness.errors import HarnessError
from litman_harness.plans import PlanStore


class Setup:
    def __init__(self, tmp_path: Path, *, incorporate: bool = True, gated: bool = False):
        self.drive = dossier_drive()
        self.store = PlanStore(tmp_path / "plans")
        self.state = AtomicSharedState(self.drive)
        self.dossier = ExpedienteService(self.drive, self.store, self.state)
        if incorporate:
            self.incorporation = self.dossier.apply_incorporation(
                self.dossier.preview_incorporation("root", ["source"]).id)
        shared = UnavailableSharedState() if gated else self.state
        self.publication = PublicationService(ExpedienteService(self.drive, self.store, shared), tmp_path / "work")
        self.core_calls: list[list[str]] = []
        self.tmp_path = tmp_path

    def analysis(self, job_type: str = "assessment") -> AnalysisService:
        base = core_run(job_type)

        def run(command, **kwargs):
            self.core_calls.append(command)
            return base(command, **kwargs)

        return AnalysisService(self.drive, self.store, work_root=self.tmp_path / "work", run=run,
                               publication=self.publication)

    def manifest(self) -> Manifest:
        resource = next(item for item in self.drive.resources.values() if item.name == "manifest.json")
        return Manifest.parse(self.drive.contents[resource.id].decode())

    def set_phase(self, phase: str) -> None:
        resource = next(item for item in self.drive.resources.values() if item.name == "manifest.json")
        manifest = self.manifest()
        manifest.workflow_phase = phase
        self.drive.write_text(resource.id, manifest.serialize())


def test_preview_includes_publication_and_validates_it_before_core(tmp_path: Path):
    with pytest.raises(HarnessError) as raised:
        Setup(tmp_path / "new", incorporate=False).analysis().preview("root", ["source"], "assessment", "codex")
    assert raised.value.code == "dossier_not_adopted"
    setup = Setup(tmp_path)
    plan = setup.analysis("detailed-analysis").preview("root", ["source"], "detailed-analysis", "codex")
    kinds = [a.kind for a in plan.actions]
    assert kinds == ["download_original", "run_core", "publish_results", "convert_live_offer", "set_phase",
                     "update_context", "update_manifest"]
    publish = next(a for a in plan.actions if a.kind == "publish_results")
    assert publish.parent_id == setup.manifest().folders["detailed"]
    assert next(a for a in plan.actions if a.kind == "set_phase").name == "analisis_detallado"
    assert setup.core_calls == []


def test_missing_offer_folder_fails_in_preview_not_after_core(tmp_path: Path):
    setup = Setup(tmp_path)
    resource = next(item for item in setup.drive.resources.values() if item.name == "manifest.json")
    manifest = setup.manifest()
    manifest.folders["offer"] = None
    setup.drive.write_text(resource.id, manifest.serialize())
    with pytest.raises(HarnessError) as raised:
        setup.analysis("detailed-analysis").preview("root", ["source"], "detailed-analysis", "codex")
    assert raised.value.code == "folder_not_registered" and setup.core_calls == []


def test_one_acceptance_runs_core_publishes_and_advances_the_phase(tmp_path: Path):
    setup = Setup(tmp_path)
    analysis = setup.analysis()
    plan = analysis.preview("root", ["source"], "assessment", "codex")
    result = analysis.execute(plan.id)
    assert result["publication"]["status"] == "succeeded"
    manifest = setup.manifest()
    assert [item["operation_id"] for item in manifest.analyses] == [plan.operation_id]
    assert manifest.workflow_phase == "analisis_inicial"
    assert result["recommended_action"]["kind"] == "propose_summary"
    assert not Path(result["workspace"]).exists()
    again = analysis.execute(plan.id)
    assert again["operation_status"] == "published" and again["publication"]["already_published"] is True


def test_detailed_analysis_converts_the_live_offer_and_phase_never_goes_back(tmp_path: Path):
    setup = Setup(tmp_path)
    analysis = setup.analysis("detailed-analysis")
    analysis.execute(analysis.preview("root", ["source"], "detailed-analysis", "codex").id)
    manifest = setup.manifest()
    assert manifest.workflow_phase == "analisis_detallado"
    assert setup.drive.resources[manifest.live_offer["document_id"]].mime_type == GOOGLE_DOC_MIME
    setup.set_phase("oferta_en_preparacion")
    assessment = setup.analysis()
    plan = assessment.preview("root", ["source"], "assessment", "codex")
    assert "set_phase" not in [a.kind for a in plan.actions]
    assessment.execute(plan.id)
    assert setup.manifest().workflow_phase == "oferta_en_preparacion"


def test_phase_set_after_preview_is_not_moved_back_at_publication(tmp_path: Path):
    setup = Setup(tmp_path)
    analysis = setup.analysis()
    plan = analysis.preview("root", ["source"], "assessment", "codex")
    assert "set_phase" in [a.kind for a in plan.actions]
    setup.set_phase("analisis_detallado")
    analysis.execute(plan.id)
    assert setup.manifest().workflow_phase == "analisis_detallado"


def test_publication_failure_is_recoverable_with_the_same_plan_id(tmp_path: Path):
    setup = Setup(tmp_path)
    analysis = setup.analysis()
    plan = analysis.preview("root", ["source"], "assessment", "codex")
    setup.state.race_before_update = {"manifest.json"}
    failed = analysis.execute(plan.id)
    assert failed["publication"]["status"] == "failed"
    assert failed["publication"]["error"]["code"] == "manifest_changed_retry"
    retry = failed["recommended_action"]
    assert (retry["kind"], retry["tool"], retry["arguments"]) == ("publish_analysis", "execute_analysis",
                                                                  {"plan_id": plan.id})
    pending = setup.dossier.status("root")
    assert pending["recommended_action"]["tool"] == "apply_publication"
    core_runs, created = len(setup.core_calls), list(setup.drive.created)
    resumed = analysis.execute(plan.id)
    assert resumed["publication"]["status"] == "succeeded" and len(setup.core_calls) == core_runs
    assert setup.drive.created == created  # uploads adopted, not repeated
    assert [item["operation_id"] for item in setup.manifest().analyses] == [plan.operation_id]


def test_publication_can_also_be_resumed_with_apply_publication(tmp_path: Path):
    setup = Setup(tmp_path)
    analysis = setup.analysis()
    plan = analysis.preview("root", ["source"], "assessment", "codex")
    setup.state.race_before_update = {"manifest.json"}
    analysis.execute(plan.id)
    publication_plan = setup.store.record(setup.drive.user, plan.operation_id).result["publication_plan_id"]
    assert setup.publication.apply(publication_plan)["status"] == "succeeded"
    assert analysis.execute(plan.id)["publication"]["already_published"] is True


def test_gate_closed_publication_keeps_the_analysis_local(tmp_path: Path):
    setup = Setup(tmp_path, gated=True)
    analysis = setup.analysis()
    plan = analysis.preview("root", ["source"], "assessment", "codex")
    result = analysis.execute(plan.id)
    assert result["publication"]["status"] == "pending_concurrency_gate"
    assert Path(result["workspace"]).is_dir() and setup.manifest().analyses == []


def test_apply_responses_include_the_next_recommended_step(tmp_path: Path):
    setup = Setup(tmp_path)
    assert setup.incorporation["recommended_action"]["kind"] == "run_assessment"
