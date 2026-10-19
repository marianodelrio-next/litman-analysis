from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest
from fakes import PDF, AtomicSharedState, dossier_drive

from litman_harness.dossier.context import context_sha256
from litman_harness.dossier.manifest import Manifest
from litman_harness.dossier.models import FOLDER_MIME, GOOGLE_DOC_MIME, Resource
from litman_harness.dossier.service import ExpedienteService
from litman_harness.errors import HarnessError
from litman_harness.plans import PlanStore


def services(tmp_path: Path, drive=None, atomic: bool = True):
    drive = drive or dossier_drive()
    state = AtomicSharedState(drive) if atomic else None
    return drive, state, ExpedienteService(drive, PlanStore(tmp_path / "plans"), state)


def incorporate(tmp_path: Path, **kwargs):
    drive, state, service = services(tmp_path)
    plan = service.preview_incorporation("root", ["source"], **kwargs)
    result = service.apply_incorporation(plan.id)
    assert result["status"] == "succeeded"
    return drive, state, service, result


def manifest_of(drive) -> tuple[Resource, Manifest]:
    resource = next(item for item in drive.resources.values() if item.name == "manifest.json")
    return resource, Manifest.parse(drive.contents[resource.id].decode())


# -- inspection and status -----------------------------------------------------------------------

def test_inspect_is_read_only_scoped_and_keeps_duplicate_names_distinct(tmp_path: Path):
    drive, _, service = services(tmp_path, atomic=False)
    drive.add(Resource("source-2", "pliego.pdf", PDF, "2", drive_id="shared", parents=("root",)), b"otro")
    result = service.inspect("root")
    assert result["writes"] is False and drive.created == []
    assert result["candidates"]["originals"] == ["source", "source-2"]
    assert result["candidates"]["offer"] == ["offer-doc"]
    assert {action["kind"] for action in result["next_actions"]} >= {"incorporate", "identify_live_offer"}
    assert set(drive.listed) == {"root"}


@pytest.mark.parametrize(("change", "code"), (
    (lambda d: d.resources.pop("root"), "not_found"),
    (lambda d: d.add(replace(d.resources["root"], mime_type=PDF)), "not_folder"),
    (lambda d: d.add(replace(d.resources["root"], trashed=True)), "trashed"),
))
def test_root_must_be_an_available_folder(tmp_path: Path, change, code):
    drive, _, service = services(tmp_path, atomic=False)
    change(drive)
    with pytest.raises(HarnessError) as raised:
        service.status("root")
    assert raised.value.code == code


def test_status_states_without_or_with_broken_litman_state(tmp_path: Path):
    drive, _, service = services(tmp_path, atomic=False)
    assert service.status("root")["state"] == "unadopted"
    drive.add(Resource("litman", "_LitMan", FOLDER_MIME, "1", drive_id="shared", parents=("root",)))
    partial = service.status("root")
    assert partial["state"] == "partial" and partial["problem"]["code"] == "manifest_missing"
    drive.add(Resource("m1", "manifest.json", "application/json", "1", drive_id="shared", parents=("litman",)), b"{")
    assert service.status("root")["problem"]["code"] == "invalid_manifest"
    drive.add(Resource("m2", "manifest.json", "application/json", "1", drive_id="shared", parents=("litman",)), b"{}")
    assert service.status("root")["problem"]["code"] == "manifest_duplicated"


def test_unknown_manifest_version_is_read_only(tmp_path: Path):
    drive, _, service = services(tmp_path, atomic=False)
    drive.add(Resource("litman", "_LitMan", FOLDER_MIME, "1", drive_id="shared", parents=("root",)))
    drive.add(Resource("m", "manifest.json", "application/json", "1", drive_id="shared", parents=("litman",)),
              json.dumps({"schema_version": "litman-dossier-v9"}).encode())
    status = service.status("root")
    assert status["state"] == "unsupported_manifest"
    assert [action["kind"] for action in status["next_actions"]] == ["review_manifest"]
    with pytest.raises(HarnessError) as raised:
        service.preview_incorporation("root", ["source"])
    assert raised.value.code == "unsupported_manifest"


def test_manifest_of_another_root_is_not_adopted(tmp_path: Path):
    drive, _, service, _ = incorporate(tmp_path)
    resource, manifest = manifest_of(drive)
    manifest.root_folder_id = "other-root"
    drive.write_text(resource.id, manifest.serialize())
    status = service.status("root")
    assert status["state"] == "partial" and status["problem"]["code"] == "invalid_manifest"


def test_adopted_status_recovers_by_id_after_rename_and_reports_moved_or_trashed(tmp_path: Path):
    drive, _, _, _ = incorporate(tmp_path)
    other_install = ExpedienteService(drive, PlanStore(tmp_path / "other-installation"))
    drive.add(replace(drive.resources["source"], name="renombrado.pdf"))
    status = other_install.status("root")
    assert status["state"] == "adopted"
    assert [item["file_id"] for item in status["manifest"]["originals"]] == ["source"]
    assert status["manifest"]["workflow_phase"] == "sin_analisis"
    assert {a["kind"] for a in status["next_actions"]} >= {"run_assessment", "run_detailed_analysis",
                                                           "identify_live_offer"}
    drive.add(replace(drive.resources["source"], parents=("elsewhere",)))
    status = other_install.status("root")
    assert status["state"] == "degraded"
    assert status["missing_resources"] == [{"kind": "original", "id": "source", "reason": "outside_tree_or_trashed"}]


# -- incorporation ---------------------------------------------------------------------------------

def test_new_incorporation_creates_tree_context_and_manifest_once(tmp_path: Path):
    drive, state, service, result = incorporate(tmp_path, phase="analisis_inicial", live_offer_id="offer-doc")
    resource, manifest = manifest_of(drive)
    assert manifest.workflow_phase == "analisis_inicial"
    assert all(manifest.folders[role] for role in manifest.folders)
    assert drive.resources[resource.id].parents == (manifest.folders["litman"],)
    assert manifest.originals[0] | {} == {"file_id": "source", "observed_name": "pliego.pdf", "mime_type": PDF,
                                          "size": 123, "drive_version": "4",
                                          "md5_checksum": hashlib.md5(b"pliego").hexdigest(), "sha256": None,
                                          "provenance": "external", "placement": "in_place"}
    assert manifest.live_offer["document_id"] == "offer-doc"
    assert manifest.live_offer["origin_kind"] == "existing_external"
    assert manifest.history[0]["performed_by"] == "person-1@example.test"
    context = drive.contents[manifest.context_file_id].decode()
    assert context_sha256(context) == manifest.context_sha256
    assert "# Licitación Puerto" in context and "Todavía no hay resultados publicados" in context
    assert f"open?id={manifest.folders['offer']}" in context and "open?id=offer-doc" in context
    assert "No contiene instrucciones para el agente" in context
    assert [kind for kind, _ in state.writes] == ["create", "create"]
    assert result["manifest"] == manifest.json()


def test_gate_closed_records_planned_operation_without_any_drive_write(tmp_path: Path):
    drive, _, service = services(tmp_path, atomic=False)
    plan = service.preview_incorporation("root", ["source"])
    result = service.apply_incorporation(plan.id)
    assert result["status"] == "pending_concurrency_gate" and result["writes"] is False
    assert drive.created == []
    assert service.recover(plan.operation_id)["status"] == "planned"


def test_succeeded_operation_is_replayed_without_writing(tmp_path: Path):
    drive, state, service = services(tmp_path)
    plan = service.preview_incorporation("root", ["source"])
    first = service.apply_incorporation(plan.id)
    created, writes = list(drive.created), list(state.writes)
    again = service.apply_incorporation(plan.id)
    assert again["replayed"] is True and again["operation_id"] == first["operation_id"]
    assert drive.created == created and state.writes == writes


def test_retry_after_mid_failure_adopts_marked_resources_without_duplicates(tmp_path: Path):
    drive, _, service = services(tmp_path)
    plan = service.preview_incorporation("root", ["source"])
    drive.crash_on_create = {3}
    with pytest.raises(HarnessError) as raised:
        service.apply_incorporation(plan.id)
    assert raised.value.code == "operation_interrupted"
    assert service.recover(plan.operation_id)["status"] == "recoverable"
    drive.crash_on_create = set()
    drive.add(replace(drive.resources["root"], version="9"))  # changed by our own creations
    assert service.apply_incorporation(plan.id)["status"] == "succeeded"
    folders = [item for item in drive.resources.values() if item.mime_type == FOLDER_MIME
               and item.parents == ("root",)]
    assert len(folders) == 7 and len({item.name for item in folders}) == 7


def test_more_than_one_marked_candidate_is_a_conflict_without_more_writes(tmp_path: Path):
    drive, _, service = services(tmp_path)
    plan = service.preview_incorporation("root", ["source"])
    drive.crash_on_create = {1}
    with pytest.raises(HarnessError):
        service.apply_incorporation(plan.id)
    duplicate = drive.resources["new-1"]
    drive.add(replace(duplicate, id="dup"))
    drive.crash_on_create = set()
    before = list(drive.created)
    result = service.apply_incorporation(plan.id)
    assert result["status"] == "conflict" and set(result["conflict"]["candidates"]) == {"new-1", "dup"}
    assert drive.created == before


def test_adopted_incorporation_proposes_only_missing_registrations(tmp_path: Path):
    drive, state, service, _ = incorporate(tmp_path)
    drive.add(Resource("annex", "anexo.pdf", PDF, "1", drive_id="shared", parents=("root",)), b"anexo")
    plan = service.preview_incorporation("root", ["source", "annex"], live_offer_id="offer-doc",
                                         phase="analisis_detallado")
    kinds = [action.kind for action in plan.actions]
    assert "create_folder" not in kinds and "create_manifest" not in kinds
    assert kinds == ["set_phase", "register_original", "place_original", "register_external_offer",
                     "update_context", "update_manifest"]
    assert service.apply_incorporation(plan.id)["status"] == "succeeded"
    _, manifest = manifest_of(drive)
    assert [item["file_id"] for item in manifest.originals] == ["source", "annex"]
    assert manifest.workflow_phase == "analisis_detallado" and len(manifest.history) == 2
    with pytest.raises(HarnessError) as raised:
        service.preview_incorporation("root", ["source"])
    assert raised.value.code == "no_changes"


def test_second_live_offer_is_rejected(tmp_path: Path):
    drive, _, service, _ = incorporate(tmp_path, live_offer_id="offer-doc")
    drive.add(Resource("offer-2", "Otra", GOOGLE_DOC_MIME, "1", drive_id="shared", parents=("root",),
                       capabilities={"canEdit": True}))
    with pytest.raises(HarnessError) as raised:
        service.preview_incorporation("root", live_offer_id="offer-2")
    assert raised.value.code == "live_offer_exists"


def test_existing_folders_can_be_registered_but_must_be_folders_of_this_tree(tmp_path: Path):
    drive, _, service = services(tmp_path)
    drive.add(Resource("orig-folder", "Pliegos", FOLDER_MIME, "1", drive_id="shared", parents=("root",)))
    for folder_ids, code in (({"originals": "source"}, "invalid_folder"), ({"bogus": "x"}, "invalid_folder_role"),
                             ({"originals": "orig-folder", "offer": "orig-folder"}, "duplicate_folder")):
        with pytest.raises(HarnessError) as raised:
            service.preview_incorporation("root", folder_ids=folder_ids)
        assert raised.value.code == code
    plan = service.preview_incorporation("root", ["source"], folder_ids={"originals": "orig-folder"})
    assert [a.resource_id for a in plan.actions if a.kind == "register_folder"] == ["orig-folder"]
    assert sum(a.kind == "create_folder" for a in plan.actions) == 6
    service.apply_incorporation(plan.id)
    assert manifest_of(drive)[1].folders["originals"] == "orig-folder"
    with pytest.raises(HarnessError) as raised:
        service.preview_incorporation("root", folder_ids={"originals": "new-1"})
    assert raised.value.code == "folder_role_registered"


def test_invalid_phase_foreign_original_and_native_original_are_rejected(tmp_path: Path):
    drive, _, service = services(tmp_path)
    drive.add(Resource("elsewhere", "x.pdf", PDF, "1", drive_id="shared", parents=("unrelated",)), b"x")
    for kwargs, code in (({"original_ids": ["source"], "phase": "fase_x"}, "invalid_phase"),
                         ({"original_ids": ["elsewhere"]}, "original_not_in_expediente"),
                         ({"original_ids": ["offer-doc"]}, "invalid_original")):
        with pytest.raises(HarnessError) as raised:
            service.preview_incorporation("root", **kwargs)
        assert raised.value.code == code


def test_stale_plan_and_other_account_are_rejected_before_writing(tmp_path: Path):
    drive, _, service = services(tmp_path)
    plan = service.preview_incorporation("root", ["source"])
    drive.add(replace(drive.resources["source"], md5_checksum="0" * 32))  # same version, other content
    with pytest.raises(HarnessError) as raised:
        service.apply_incorporation(plan.id)
    assert raised.value.code == "stale_plan" and raised.value.details["reason"] == "content_changed"
    assert drive.created == []
    drive.add(replace(drive.resources["source"], md5_checksum=hashlib.md5(b"pliego").hexdigest()))
    drive.user = "person-2"
    with pytest.raises(HarnessError) as raised:
        service.apply_incorporation(plan.id)
    assert raised.value.code == "unknown_plan" and drive.created == []


def test_context_edited_outside_litman_does_not_block_and_is_not_overwritten(tmp_path: Path):
    drive, _, service, _ = incorporate(tmp_path)
    _, before = manifest_of(drive)
    drive.write_text(before.context_file_id, "# editado a mano\n")
    plan = service.preview_incorporation("root", phase="analisis_inicial")
    result = service.apply_incorporation(plan.id)
    assert result["status"] == "succeeded"
    conflict = result["context_conflict"]
    assert conflict["file_id"] == before.context_file_id and conflict["reason"] == "edited_outside_litman"
    assert "Fase confirmada: `analisis_inicial`" in conflict["proposed_content"]
    assert drive.contents[before.context_file_id] == b"# editado a mano\n"
    _, after = manifest_of(drive)
    assert after.workflow_phase == "analisis_inicial" and after.context_sha256 == before.context_sha256


def test_overwrite_context_resolves_the_conflict_explicitly(tmp_path: Path):
    drive, _, service, _ = incorporate(tmp_path)
    _, before = manifest_of(drive)
    drive.write_text(before.context_file_id, "# editado a mano\n")
    plan = service.preview_incorporation("root", overwrite_context=True)
    action = next(a for a in plan.actions if a.kind == "replace_context")
    assert action.metadata["effect"] == "sobrescribe ediciones externas"
    assert action.metadata["current_sha256"] == context_sha256("# editado a mano\n")
    result = service.apply_incorporation(plan.id)
    assert result["status"] == "succeeded" and result["context_conflict"] is None
    _, after = manifest_of(drive)
    written = drive.contents[after.context_file_id].decode()
    assert written.startswith("# Licitación Puerto") and after.context_sha256 == context_sha256(written)
    next_plan = service.preview_incorporation("root", phase="analisis_inicial")
    assert service.apply_incorporation(next_plan.id)["context_conflict"] is None


def test_overwrite_context_is_rejected_if_the_content_changed_again(tmp_path: Path):
    drive, _, service, _ = incorporate(tmp_path)
    _, before = manifest_of(drive)
    drive.write_text(before.context_file_id, "# editado a mano\n")
    plan = service.preview_incorporation("root", overwrite_context=True)
    drive.write_text(before.context_file_id, "# editado otra vez\n")
    result = service.apply_incorporation(plan.id)
    assert result["status"] == "succeeded"
    assert result["context_conflict"]["reason"] == "context_changed_since_preview"
    assert drive.contents[before.context_file_id] == b"# editado otra vez\n"


def test_crash_between_manifest_and_context_resumes_writing_the_context(tmp_path: Path):
    drive, state, service, _ = incorporate(tmp_path)
    _, before = manifest_of(drive)
    plan = service.preview_incorporation("root", phase="analisis_detallado")
    state.crash_after_update = {"manifest.json"}
    with pytest.raises(HarnessError) as raised:
        service.apply_incorporation(plan.id)
    assert raised.value.code == "operation_interrupted"
    assert "analisis_detallado" not in drive.contents[before.context_file_id].decode()
    result = service.apply_incorporation(plan.id)
    assert result["status"] == "succeeded" and result["context_conflict"] is None
    _, after = manifest_of(drive)
    context = drive.contents[after.context_file_id].decode()
    assert "Fase confirmada: `analisis_detallado`" in context and after.context_sha256 == context_sha256(context)


def test_manifest_content_changed_since_preview_is_a_conflict(tmp_path: Path):
    drive, _, service, _ = incorporate(tmp_path)
    plan = service.preview_incorporation("root", phase="analisis_inicial")
    resource, manifest = manifest_of(drive)
    manifest.workflow_phase = "entregada"
    drive.write_text(resource.id, manifest.serialize())
    result = service.apply_incorporation(plan.id)
    assert result["status"] == "conflict"
    assert manifest_of(drive)[1].workflow_phase == "entregada"


def test_manifest_version_bump_without_content_change_is_not_a_conflict(tmp_path: Path):
    drive, state, service, _ = incorporate(tmp_path)
    plan = service.preview_incorporation("root", phase="analisis_inicial")
    resource, manifest = manifest_of(drive)
    assert next(a for a in plan.actions if a.kind == "update_manifest").expected_version is None
    drive.write_text(resource.id, manifest.serialize())  # Drive version moves, content does not
    assert service.apply_incorporation(plan.id)["status"] == "succeeded"
    assert manifest_of(drive)[1].workflow_phase == "analisis_inicial"

def test_status_never_lists_or_reads_other_dossiers(tmp_path: Path):
    drive, _, service, _ = incorporate(tmp_path)
    service.status("root")
    service.inspect("root")
    assert not {"other-root", "other-file"} & set(drive.gets + drive.listed)


def test_folder_outside_the_connected_tree_cannot_be_registered(tmp_path: Path):
    drive, _, service = services(tmp_path)
    drive.add(Resource("loose", "Oferta", FOLDER_MIME, "1", drive_id="shared", parents=("unrelated",)))
    with pytest.raises(HarnessError) as raised:
        service.preview_incorporation("root", folder_ids={"offer": "loose"})
    assert raised.value.code == "invalid_folder"


def test_context_links_by_id_survive_renames(tmp_path: Path):
    drive, _, service, _ = incorporate(tmp_path)
    _, manifest = manifest_of(drive)
    offer_folder = manifest.folders["offer"]
    drive.add(replace(drive.resources[offer_folder], name="Oferta renombrada"))
    assert service.status("root")["state"] == "adopted"
    assert f"open?id={offer_folder}" in drive.contents[manifest.context_file_id].decode()


def test_adopted_incorporation_through_drive_v2_writes_with_the_read_etag(tmp_path: Path):
    from fakes import FakeDriveHttp

    from litman_harness.adapters.drive_state import DriveSharedState
    drive, _, _, _ = incorporate(tmp_path)
    http = FakeDriveHttp(drive)
    service = ExpedienteService(drive, PlanStore(tmp_path / "plans"), DriveSharedState(http, drive))
    plan = service.preview_incorporation("root", phase="analisis_inicial")
    assert "root" not in plan.snapshot
    result = service.apply_incorporation(plan.id)
    assert result["status"] == "succeeded" and result["context_conflict"] is None
    puts = [(url.rsplit("/", 1)[1], headers["If-Match"]) for method, url, _, headers, _ in http.requests
            if method == "PUT"]
    resource, manifest = manifest_of(drive)
    assert puts == [(resource.id, '"e1"'), (manifest.context_file_id, '"e1"')]
    assert manifest.workflow_phase == "analisis_inicial"


def test_version_changes_without_content_changes_do_not_invalidate_incorporation(tmp_path: Path):
    drive, _, service = services(tmp_path)
    drive.add(Resource("orig-folder", "Pliegos", FOLDER_MIME, "1", drive_id="shared", parents=("root",)))
    plan = service.preview_incorporation("root", ["source"], folder_ids={"originals": "orig-folder"})
    assert plan.snapshot == {"source": hashlib.md5(b"pliego").hexdigest()}
    for identifier, version in (("root", "9"), ("orig-folder", "5"), ("source", "8")):
        drive.add(replace(drive.resources[identifier], version=version))
    assert service.apply_incorporation(plan.id)["status"] == "succeeded"


def test_original_without_md5_is_rejected_in_incorporation_preview(tmp_path: Path):
    drive, _, service = services(tmp_path)
    drive.add(replace(drive.resources["source"], md5_checksum=None))
    with pytest.raises(HarnessError) as raised:
        service.preview_incorporation("root", ["source"])
    assert raised.value.code == "missing_checksum"


def test_old_manifest_originals_without_md5_still_parse(tmp_path: Path):
    drive, _, service, _ = incorporate(tmp_path)
    resource, manifest = manifest_of(drive)
    for original in manifest.originals:
        original.pop("md5_checksum")
    drive.write_text(resource.id, manifest.serialize())
    assert service.status("root")["state"] == "adopted"
    assert "md5_checksum" not in Manifest.parse(drive.contents[resource.id].decode()).originals[0]


# -- placement of originals ------------------------------------------------------------------------

MOVE, COPY = {"canDownload": True, "canMoveItemWithinDrive": True, "canCopy": True}, {"canDownload": True,
                                                                                      "canCopy": True}


def with_original(tmp_path: Path, capabilities: dict[str, bool], identifier: str = "tender"):
    drive, state, service = services(tmp_path)
    drive.add(Resource(identifier, "pliego-tecnico.pdf", PDF, "3", 77, "shared", ("root",),
                       capabilities=capabilities), b"tecnico")
    return drive, state, service


def placement(plan) -> list:
    return [action for action in plan.actions if action.kind == "place_original"]


def legacy_misplaced(drive, capabilities: dict[str, bool]) -> None:
    """A dossier registered before placement existed: ``source`` sits in the root without ``placement``."""
    resource, manifest = manifest_of(drive)
    manifest.originals[0].pop("placement")
    drive.write_text(resource.id, manifest.serialize())
    drive.add(replace(drive.resources["source"], capabilities=capabilities))


def test_movable_original_is_moved_into_originals_keeping_its_id(tmp_path: Path):
    drive, _, service = with_original(tmp_path, MOVE)
    plan = service.preview_incorporation("root", ["tender"])
    [action] = placement(plan)
    assert action.resource_id == "tender" and action.metadata["strategy"] == "move"
    assert action.metadata["warning"] is None and action.metadata["registered"] is False
    result = service.apply_incorporation(plan.id)
    _, manifest = manifest_of(drive)
    assert drive.resources["tender"].parents == (manifest.folders["originals"],)
    assert manifest.originals[0]["file_id"] == "tender" and manifest.originals[0]["provenance"] == "external"
    assert "placement" not in manifest.originals[0] and "copied_from" not in manifest.originals[0]
    assert result["placement_warnings"] == [] and drive.moved == ["tender"]
    assert "tender" not in service.status("root")["candidates"]["originals"]


def test_copy_only_original_is_copied_and_the_source_is_hidden_from_status(tmp_path: Path):
    drive, _, service = with_original(tmp_path, COPY)
    source = drive.resources["tender"]
    plan = service.preview_incorporation("root", ["tender"])
    [action] = placement(plan)
    assert action.metadata["strategy"] == "copy" and "copia" in action.metadata["warning"]
    result = service.apply_incorporation(plan.id)
    _, manifest = manifest_of(drive)
    [copy] = [item for item in drive.resources.values() if item.parents == (manifest.folders["originals"],)]
    assert copy.name == source.name and copy.md5_checksum == source.md5_checksum
    assert copy.app_properties["litman_operation_id"] == plan.operation_id
    assert copy.app_properties["litman_action_id"]
    assert drive.resources["tender"] == source and drive.moved == []
    entry = manifest.originals[0]
    assert entry["file_id"] == copy.id and entry["copied_from"] == "tender" and entry["provenance"] == "copied"
    assert entry["md5_checksum"] == source.md5_checksum and entry["observed_name"] == source.name
    assert result["placement_warnings"] == [action.metadata["warning"]]
    assert "tender" not in service.status("root")["candidates"]["originals"]
    assert "tender" in service.inspect("root")["candidates"]["originals"]
    with pytest.raises(HarnessError) as raised:  # the source is already registered through its copy
        service.preview_incorporation("root", ["tender"])
    assert raised.value.code == "no_changes"


@pytest.mark.parametrize("capabilities", ({"canDownload": True},
                                          {"canDownload": True, "canMoveItemWithinDrive": False, "canCopy": False}))
def test_original_that_cannot_be_moved_or_copied_stays_in_place_with_a_warning(tmp_path: Path, capabilities):
    drive, _, service = with_original(tmp_path, capabilities)
    plan = service.preview_incorporation("root", ["tender"])
    [action] = placement(plan)
    assert action.metadata["strategy"] == "in_place" and "ni copiar" in action.metadata["warning"]
    result = service.apply_incorporation(plan.id)
    _, manifest = manifest_of(drive)
    assert manifest.originals[0]["file_id"] == "tender" and manifest.originals[0]["placement"] == "in_place"
    assert drive.resources["tender"].parents == ("root",)
    assert result["placement_warnings"] == [action.metadata["warning"]]
    status = service.status("root")
    assert status["recommended_action"]["kind"] == "run_assessment"
    assert status["recommended_action"]["arguments"]["original_ids"] == ["tender"]


def test_original_already_inside_originals_is_only_registered(tmp_path: Path):
    drive, _, service = services(tmp_path)
    drive.add(Resource("orig-folder", "Pliegos", FOLDER_MIME, "1", drive_id="shared", parents=("root",)))
    drive.add(Resource("inside", "pliego.pdf", PDF, "1", 5, "shared", ("orig-folder",), capabilities=MOVE), b"x")
    plan = service.preview_incorporation("root", ["inside"], folder_ids={"originals": "orig-folder"})
    assert placement(plan) == []
    assert service.apply_incorporation(plan.id)["placement_warnings"] == []
    assert drive.moved == [] and manifest_of(drive)[1].originals[0]["file_id"] == "inside"


def test_rejected_move_falls_back_to_copy(tmp_path: Path):
    drive, _, service = with_original(tmp_path, MOVE)
    drive.move_denied = {"tender"}
    plan = service.preview_incorporation("root", ["tender"])
    assert placement(plan)[0].metadata["strategy"] == "move"
    result = service.apply_incorporation(plan.id)
    entry = manifest_of(drive)[1].originals[0]
    assert entry["copied_from"] == "tender" and entry["provenance"] == "copied" and entry["file_id"] != "tender"
    assert drive.resources["tender"].parents == ("root",) and len(result["placement_warnings"]) == 1


def test_rejected_move_without_copy_stays_in_place(tmp_path: Path):
    drive, _, service = with_original(tmp_path, {"canDownload": True, "canMoveItemWithinDrive": True})
    drive.move_denied = {"tender"}
    result = service.apply_incorporation(service.preview_incorporation("root", ["tender"]).id)
    assert manifest_of(drive)[1].originals[0]["placement"] == "in_place"
    assert "ni copiar" in result["placement_warnings"][0]


def test_interrupted_copy_is_adopted_on_resume_without_a_second_copy(tmp_path: Path):
    drive, _, service = with_original(tmp_path, MOVE)
    drive.move_denied = {"tender"}
    plan = service.preview_incorporation("root", ["tender"])
    drive.crash_on_create = {sum(action.kind == "create_folder" for action in plan.actions) + 1}  # the copy
    with pytest.raises(HarnessError) as raised:
        service.apply_incorporation(plan.id)
    assert raised.value.code == "operation_interrupted"
    drive.crash_on_create = set()
    assert service.apply_incorporation(plan.id)["status"] == "succeeded"
    _, manifest = manifest_of(drive)
    copies = [item for item in drive.resources.values() if item.name == "pliego-tecnico.pdf"
              and item.parents == (manifest.folders["originals"],)]
    assert len(copies) == 1 and manifest.originals[0]["file_id"] == copies[0].id


def test_registered_original_outside_originals_is_organized_from_status(tmp_path: Path):
    drive, _, service, _ = incorporate(tmp_path)
    legacy_misplaced(drive, COPY)
    status = service.status("root")
    assert status["recommended_action"]["kind"] == "organize_originals"
    assert status["recommended_action"]["tool"] == "preview_incorporation"
    plan = service.preview_incorporation(**status["recommended_action"]["arguments"])
    assert [action.kind for action in plan.actions] == ["place_original", "update_context", "update_manifest"]
    assert placement(plan)[0].metadata["registered"] is True
    assert service.apply_incorporation(plan.id)["status"] == "succeeded"
    _, manifest = manifest_of(drive)
    entry = manifest.originals[0]
    assert entry["copied_from"] == "source" and entry["provenance"] == "copied"
    assert entry["md5_checksum"] == hashlib.md5(b"pliego").hexdigest()
    assert manifest.summary_sources()["source"] == "original"
    status = service.status("root")
    assert status["recommended_action"]["kind"] == "run_assessment"
    assert status["recommended_action"]["arguments"]["original_ids"] == [entry["file_id"]]


def test_registered_original_with_changed_content_is_not_placed(tmp_path: Path):
    drive, _, service, _ = incorporate(tmp_path)
    legacy_misplaced(drive, MOVE)
    drive.write_text("source", "otro contenido")
    assert service.status("root")["recommended_action"]["kind"] == "run_assessment"
    with pytest.raises(HarnessError) as raised:
        service.preview_incorporation("root")
    assert raised.value.code == "no_changes" and "cambió" in raised.value.details["placement_warnings"][0]
    plan = service.preview_incorporation("root", phase="analisis_inicial")
    [action] = placement(plan)
    assert action.metadata["strategy"] == "skipped"
    result = service.apply_incorporation(plan.id)
    assert result["status"] == "succeeded" and result["placement_warnings"] == [action.metadata["warning"]]
    assert drive.moved == [] and manifest_of(drive)[1].originals[0]["file_id"] == "source"


@pytest.mark.parametrize("change", (lambda item: replace(item, trashed=True),
                                    lambda item: replace(item, parents=("elsewhere",))))
def test_registered_original_outside_the_dossier_is_not_recommended_for_placement(tmp_path: Path, change):
    drive, _, service, _ = incorporate(tmp_path)
    legacy_misplaced(drive, MOVE)
    drive.add(change(drive.resources["source"]))
    status = service.status("root")
    assert status["state"] == "degraded" and status["recommended_action"]["kind"] == "run_assessment"
    with pytest.raises(HarnessError) as raised:
        service.preview_incorporation("root")
    assert raised.value.code == "no_changes"
