from __future__ import annotations

import pytest

from litman_harness.dossier.manifest import Manifest
from litman_harness.dossier.models import FOLDER_MIME, Resource
from litman_harness.dossier.recommendation import recommend

ROOT = Resource("root", "Licitación", FOLDER_MIME, "1", drive_id="shared")


def manifest(*, originals=True, analyses=(), summary_on=None) -> Manifest:
    value = Manifest.new(ROOT)
    if originals:
        value.originals = [{"file_id": "pliego"}]
    value.analyses = [{"operation_id": op, "type": kind, "status": "published", "artifacts": []}
                      for op, kind in analyses]
    if summary_on is not None:
        value.summary = {"items": [], "based_on_analyses": list(summary_on)}
    return value


def kind(**kwargs):
    action = recommend(folder_id="root", **kwargs)
    return action and action["kind"]


@pytest.mark.parametrize(("arguments", "expected"), (
    ({"state": "unadopted", "manifest": None, "candidates": {"originals": ["a", "b"]}}, "incorporate"),
    ({"state": "adopted", "manifest": manifest(originals=False)}, "incorporate"),
    ({"state": "adopted", "manifest": manifest(), "candidates": {"originals": ["otro"]}}, "run_assessment"),
    ({"state": "adopted", "manifest": manifest()}, "run_assessment"),
    ({"state": "adopted", "manifest": manifest(analyses=[("a1", "assessment")])}, "propose_summary"),
    ({"state": "adopted", "manifest": manifest(analyses=[("a1", "assessment")], summary_on=["a1"])},
     "decide_detailed_analysis"),
    ({"state": "adopted", "manifest": manifest(analyses=[("a1", "assessment"), ("d1", "detailed-analysis")],
                                               summary_on=["a1"])}, "refresh_summary"),
    ({"state": "adopted", "manifest": manifest(analyses=[("a1", "assessment"), ("d1", "detailed-analysis")],
                                               summary_on=["a1", "d1"])}, None),
    ({"state": "adopted", "manifest": manifest(), "pending": [{"operation_id": "x"}]}, "publish_analysis"),
    ({"state": "adopted", "manifest": manifest(), "misplaced_originals": ["pliego"]}, "organize_originals"),
    ({"state": "adopted", "manifest": manifest(analyses=[("a1", "assessment")], summary_on=["a1"]),
      "misplaced_originals": ["pliego"]}, "organize_originals"),
    ({"state": "adopted", "manifest": manifest(), "pending": [{"operation_id": "x"}],
      "misplaced_originals": ["pliego"]}, "publish_analysis"),
    ({"state": "partial", "manifest": None}, "review_manifest"),
    ({"state": "unsupported_manifest", "manifest": None}, "review_manifest"),
))
def test_recommendation_follows_the_guided_order(arguments, expected):
    assert kind(**arguments) == expected


def test_recommendations_carry_tool_and_arguments():
    first = recommend(folder_id="root", state="unadopted", manifest=None,
                      candidates={"originals": ["a"], "suggested_folder_ids": {"originals": "dir"}})
    assert first["tool"] == "preview_incorporation" and first["arguments"] == {
        "folder_id": "root", "suggested_original_ids": ["a"], "suggested_folder_ids": {"originals": "dir"}}
    assessment = recommend(folder_id="root", state="adopted", manifest=manifest())
    assert assessment["arguments"] == {"folder_id": "root", "original_ids": ["pliego"], "job_type": "assessment"}
    pending = recommend(folder_id="root", state="adopted", manifest=manifest(),
                        pending=[{"operation_id": "x", "publication_plan_id": "p"}])
    assert pending["tool"] == "apply_publication" and pending["arguments"] == {"plan_id": "p"}
    assert all(isinstance(action["reason"], str) and action["reason"] for action in (first, assessment, pending))


def test_registered_originals_with_published_analyses_do_not_force_incorporation():
    analysed = manifest(analyses=[("a1", "assessment")])
    assert kind(state="adopted", manifest=analysed, candidates={"originals": ["nuevo"]}) == "propose_summary"


def test_unregistered_candidates_do_not_loop_once_originals_are_registered(tmp_path):
    from fakes import AtomicSharedState, PDF, dossier_drive

    from litman_harness.dossier.service import ExpedienteService
    from litman_harness.plans import PlanStore
    drive = dossier_drive()
    service = ExpedienteService(drive, PlanStore(tmp_path / "plans"), AtomicSharedState(drive))
    assert service.status("root")["recommended_action"]["kind"] == "incorporate"
    service.apply_incorporation(service.preview_incorporation("root", ["source"]).id)
    drive.add(Resource("not-a-pliego", "notas.pdf", PDF, "1", drive_id="shared", parents=("root",)), b"notas")
    status = service.status("root")
    assert status["candidates"]["originals"] == ["not-a-pliego"]
    assert status["recommended_action"]["kind"] == "run_assessment"
    assert "incorporate" in [action["kind"] for action in status["next_actions"]]


def test_original_kept_in_place_reaches_the_assessment_without_looping(tmp_path):
    from fakes import AtomicSharedState, dossier_drive

    from litman_harness.dossier.service import ExpedienteService
    from litman_harness.plans import PlanStore
    drive = dossier_drive()  # ``source`` reports neither canMoveItemWithinDrive nor canCopy
    service = ExpedienteService(drive, PlanStore(tmp_path / "plans"), AtomicSharedState(drive))
    result = service.apply_incorporation(service.preview_incorporation("root", ["source"]).id)
    assert result["placement_warnings"] and result["recommended_action"]["kind"] == "run_assessment"
    assert service.status("root")["recommended_action"]["kind"] == "run_assessment"
