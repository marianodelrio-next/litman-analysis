from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fakes import AtomicSharedState, dossier_drive

from litman_harness.dossier.file_changes import FileChangeService
from litman_harness.dossier.manifest import Manifest
from litman_harness.dossier.models import (FOLDER_MIME, GOOGLE_DOC_MIME, GOOGLE_SHEET_MIME, XLSX_MIME,
                                           Resource)
from litman_harness.dossier.service import ExpedienteService
from litman_harness.errors import HarnessError
from litman_harness.plans import PlanStore

PDF = "application/pdf"
FULL_CAPS = {"canRename": True, "canMoveItemWithinDrive": True, "canCopy": True, "canTrash": True,
            "canDownload": True, "canAddChildren": True, "canListChildren": True}


class Setup:
    """A dossier incorporated with ``source`` (left in place, no move/copy permission) as its one original."""

    def __init__(self, tmp_path: Path):
        self.drive = dossier_drive()
        self.store = PlanStore(tmp_path / "plans")
        self.state = AtomicSharedState(self.drive)
        self.dossier = ExpedienteService(self.drive, self.store, self.state)
        self.service = FileChangeService(self.dossier)
        plan = self.dossier.preview_incorporation("root", ["source"])
        assert self.dossier.apply_incorporation(plan.id)["status"] == "succeeded"
        self.drive.add(Resource("dest", "Destino", FOLDER_MIME, "1", drive_id="shared", parents=("root",),
                                capabilities=dict(FULL_CAPS)))
        self.drive.add(Resource("loose", "suelto.pdf", PDF, "1", 10, "shared", parents=("root",),
                                capabilities=dict(FULL_CAPS)), b"contenido")

    def manifest(self) -> Manifest:
        resource = next(item for item in self.drive.resources.values() if item.name == "manifest.json")
        return Manifest.parse(self.drive.contents[resource.id].decode())

    def preview(self, operations: list[dict]) -> dict:
        return self.service.preview("root", operations)

    def apply(self, plan_id: str) -> dict:
        return self.service.apply(plan_id)

    def plans(self) -> list[Path]:
        directory = self.store.root / "person-1"
        return sorted(directory.glob("*.json")) if directory.is_dir() else []


# -- preview validation ----------------------------------------------------------------------------

def test_create_folder_rename_and_trash_are_previewed_with_paths_and_names(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.drive.add(Resource("trashme", "basura.pdf", PDF, "1", 1, "shared", parents=("root",),
                             capabilities=dict(FULL_CAPS)))
    result = setup.preview([
        {"op": "create_folder", "parent_folder_id": "dest", "name": "Nueva"},
        {"op": "rename", "file_id": "loose", "name": "renombrado.pdf"},
        {"op": "trash", "file_id": "trashme"},
    ])
    ops = result["operations"]
    assert ops[0]["resulting_name"] == "Nueva" and ops[0]["destination_path"] == "Destino"
    assert ops[1]["source_name"] == "suelto.pdf" and ops[1]["resulting_name"] == "renombrado.pdf"
    assert ops[1]["destination_path"] == ""  # directly below the root
    assert ops[2]["source_name"] == "basura.pdf" and ops[2]["destination_path"] is None


def test_move_and_copy_resolve_destination_and_resulting_name(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.drive.add(Resource("loose2", "otro.pdf", PDF, "1", 1, "shared", parents=("root",),
                             capabilities=dict(FULL_CAPS)))
    result = setup.preview([
        {"op": "move", "file_id": "loose", "parent_folder_id": "dest"},
        {"op": "copy", "file_id": "loose2", "parent_folder_id": "dest", "name": "copia.pdf"},
    ])
    ops = result["operations"]
    assert ops[0]["resulting_name"] == "suelto.pdf" and ops[0]["destination_path"] == "Destino"
    assert ops[1]["resulting_name"] == "copia.pdf"


def test_file_outside_the_tree_or_below_litman_is_rejected_before_storing_a_plan(tmp_path: Path):
    setup = Setup(tmp_path)
    before = setup.plans()
    setup.drive.forbidden.discard("other-file")
    setup.drive.forbidden.discard("other-root")
    litman = next(item for item in setup.drive.resources.values() if item.name == "_LitMan")
    for file_id in ("other-file", litman.id):
        with pytest.raises(HarnessError) as raised:
            setup.preview([{"op": "trash", "file_id": file_id}])
        assert raised.value.code == "document_outside_tree"
    with pytest.raises(HarnessError) as raised:
        setup.preview([{"op": "move", "file_id": "loose", "parent_folder_id": "other-root"}])
    assert raised.value.code == "invalid_parent"
    assert setup.plans() == before


def test_protected_resources_are_refused_and_trash_checks_the_whole_subtree(tmp_path: Path):
    setup = Setup(tmp_path)
    before = setup.plans()
    manifest = setup.manifest()
    for file_id in ("root", manifest.context_file_id):
        with pytest.raises(HarnessError) as raised:
            setup.preview([{"op": "rename", "file_id": file_id, "name": "x"}])
        assert raised.value.code == "protected_resource"
    # _LitMan itself is intercepted earlier, as outside the readable tree.
    with pytest.raises(HarnessError) as raised:
        setup.preview([{"op": "rename", "file_id": manifest.folders["litman"], "name": "x"}])
    assert raised.value.code == "document_outside_tree"
    for operation in ({"op": "move", "file_id": "source", "parent_folder_id": "dest"},
                      {"op": "trash", "file_id": "source"}):
        with pytest.raises(HarnessError) as raised:
            setup.preview([operation])
        assert raised.value.code == "protected_resource"
    # Managed renames require reconciliation.
    setup.drive.resources["source"] = replace(setup.drive.resources["source"],
                                              capabilities={**setup.drive.resources["source"].capabilities,
                                                            "canRename": True})
    with pytest.raises(HarnessError) as raised:
        setup.preview([{"op": "rename", "file_id": "source", "name": "renombrado.pdf"}])
    assert raised.value.code == "managed_rename_requires_reconciliation"
    allowed = setup.plans()
    # Trashing the folder that holds a registered original is refused too.
    originals_folder = manifest.folders["originals"]
    with pytest.raises(HarnessError) as raised:
        setup.preview([{"op": "trash", "file_id": originals_folder}])
    assert raised.value.code == "protected_resource"
    assert setup.plans() == allowed and len(allowed) == len(before)


def test_move_into_itself_or_a_descendant_is_invalid_move(tmp_path: Path):
    setup = Setup(tmp_path)
    before = setup.plans()
    setup.drive.add(Resource("dest-child", "Hijo", FOLDER_MIME, "1", drive_id="shared", parents=("dest",),
                             capabilities=dict(FULL_CAPS)))
    with pytest.raises(HarnessError) as raised:
        setup.preview([{"op": "move", "file_id": "dest", "parent_folder_id": "dest-child"}])
    assert raised.value.code == "invalid_move"
    assert setup.plans() == before


@pytest.mark.parametrize("name", ["", "x" * 201, "bad\x00name"])
def test_invalid_names_are_rejected(tmp_path: Path, name: str):
    setup = Setup(tmp_path)
    before = setup.plans()
    with pytest.raises(HarnessError) as raised:
        setup.preview([{"op": "rename", "file_id": "loose", "name": name}])
    assert raised.value.code == "invalid_request"
    assert setup.plans() == before


def test_a_file_used_in_two_operations_is_invalid_request(tmp_path: Path):
    setup = Setup(tmp_path)
    before = setup.plans()
    with pytest.raises(HarnessError) as raised:
        setup.preview([{"op": "rename", "file_id": "loose", "name": "a.pdf"},
                       {"op": "trash", "file_id": "loose"}])
    assert raised.value.code == "invalid_request"
    assert setup.plans() == before


def test_name_exists_covers_existing_children_and_names_earlier_in_the_same_plan(tmp_path: Path):
    setup = Setup(tmp_path)
    before = setup.plans()
    setup.drive.add(Resource("rival", "copia.pdf", PDF, "1", 1, "shared", parents=("dest",)), b"x")
    with pytest.raises(HarnessError) as raised:
        setup.preview([{"op": "copy", "file_id": "loose", "parent_folder_id": "dest", "name": "copia.pdf"}])
    assert raised.value.code == "name_exists"
    with pytest.raises(HarnessError) as raised:
        setup.preview([{"op": "create_folder", "parent_folder_id": "root", "name": "Nueva"},
                       {"op": "rename", "file_id": "loose", "name": "Nueva"}])
    assert raised.value.code == "name_exists"
    assert setup.plans() == before


def test_unsupported_conversion_covers_bad_format_inconvertible_source_and_folder_copy(tmp_path: Path):
    setup = Setup(tmp_path)
    before = setup.plans()
    setup.drive.add(Resource("sheet", "Hoja", GOOGLE_SHEET_MIME, "1", drive_id="shared", parents=("root",),
                             capabilities=dict(FULL_CAPS)))
    for operation in ({"op": "export", "file_id": "offer-doc", "format": "csv", "parent_folder_id": "dest",
                       "name": "x.csv"},
                      {"op": "convert", "file_id": "sheet", "parent_folder_id": "dest", "name": "x"},
                      {"op": "copy", "file_id": "dest", "parent_folder_id": "root", "name": "Copia"}):
        with pytest.raises(HarnessError) as raised:
            setup.preview([operation])
        assert raised.value.code == "unsupported_conversion"
    assert setup.plans() == before


def test_missing_capabilities_are_batched_into_one_error_listing_every_operation(tmp_path: Path):
    setup = Setup(tmp_path)
    before = setup.plans()
    setup.drive.add(Resource("no-rename", "sinrenombrar.pdf", PDF, "1", 1, "shared", parents=("root",),
                             capabilities={"canTrash": True}))
    setup.drive.add(Resource("no-add", "SinPermiso", FOLDER_MIME, "1", drive_id="shared", parents=("root",),
                             capabilities={}))
    with pytest.raises(HarnessError) as raised:
        setup.preview([{"op": "rename", "file_id": "no-rename", "name": "x.pdf"},
                       {"op": "create_folder", "parent_folder_id": "no-add", "name": "Y"},
                       {"op": "trash", "file_id": "loose"}])
    assert raised.value.code == "insufficient_capability"
    violations = raised.value.details["violations"]
    assert {(v["operation"], v["capability"]) for v in violations} == {(0, "canRename"), (1, "canAddChildren")}
    assert setup.plans() == before
    # The same plan without the blocked operations succeeds.
    setup.preview([{"op": "trash", "file_id": "no-rename"}])


# -- apply -------------------------------------------------------------------------------------

def test_create_folder_and_copy_are_applied_and_resumed_by_markers(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview([{"op": "create_folder", "parent_folder_id": "dest", "name": "Nueva"},
                          {"op": "copy", "file_id": "loose", "parent_folder_id": "dest", "name": "copia.pdf"}])
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded"
    created_ids = {output["resource_id"] for output in result["results"]}
    assert all(setup.drive.resources[identifier].parents == ("dest",) for identifier in created_ids)
    # Resuming the same plan does not create a second pair of resources.
    before = set(setup.drive.created)
    again = setup.apply(plan["plan_id"])
    assert again["replayed"] is True and set(setup.drive.created) == before


def test_export_and_convert_create_marked_resources_with_the_requested_mime_type(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.drive.resources["offer-doc"] = replace(setup.drive.resources["offer-doc"], capabilities=dict(FULL_CAPS))
    setup.drive.exports[("offer-doc", PDF)] = b"exported pdf"
    setup.drive.add(Resource("book", "tabla.xlsx", XLSX_MIME, "1", 10, "shared", parents=("root",),
                             capabilities=dict(FULL_CAPS)), b"xlsx content")
    plan = setup.preview([
        {"op": "export", "file_id": "offer-doc", "format": "pdf", "parent_folder_id": "dest",
         "name": "oferta.pdf"},
        {"op": "convert", "file_id": "book", "parent_folder_id": "dest", "name": "Tabla"},
    ])

    result = setup.apply(plan["plan_id"])

    assert result["status"] == "succeeded"
    exported, converted = (setup.drive.resources[output["resource_id"]] for output in result["results"])
    assert (exported.name, exported.mime_type, setup.drive.contents[exported.id]) == ("oferta.pdf", PDF, b"exported pdf")
    assert (converted.name, converted.mime_type) == ("Tabla", GOOGLE_SHEET_MIME)
    before = set(setup.drive.created)
    assert setup.apply(plan["plan_id"])["replayed"] is True
    assert set(setup.drive.created) == before


def test_rename_completes_without_a_call_when_already_renamed(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview([{"op": "rename", "file_id": "loose", "name": "ya-renombrado.pdf"}])
    setup.drive.rename("loose", "ya-renombrado.pdf")  # an interrupted attempt already wrote this
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded" and setup.drive.get("loose").name == "ya-renombrado.pdf"
    repeat = setup.apply(plan["plan_id"])
    assert repeat["replayed"] is True


def test_move_completes_without_a_call_when_already_moved(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview([{"op": "move", "file_id": "loose", "parent_folder_id": "dest"}])
    setup.drive.move("loose", "dest", ("root",))  # an interrupted attempt already moved it
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded" and setup.drive.get("loose").parents == ("dest",)


def test_trash_completes_without_a_call_when_already_trashed(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview([{"op": "trash", "file_id": "loose"}])
    setup.drive.trash("loose")  # an interrupted attempt already trashed it
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded" and setup.drive.get("loose").trashed is True
    repeat = setup.apply(plan["plan_id"])
    assert repeat["replayed"] is True


def test_apply_wraps_protection_capability_and_name_exists_into_conflicts(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview([{"op": "rename", "file_id": "loose", "name": "renombrado.pdf"}])
    # The capability disappears between the preview and the acceptance.
    setup.drive.resources["loose"] = setup.drive.resources["loose"].__class__(
        **{**setup.drive.resources["loose"].__dict__, "capabilities": {}})
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "conflict" and result["conflict"]["code"] == "insufficient_capability"


def test_apply_reports_insufficient_permission_as_a_conflict_without_undoing_earlier_actions(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview([{"op": "create_folder", "parent_folder_id": "dest", "name": "Nueva"},
                          {"op": "move", "file_id": "loose", "parent_folder_id": "dest"}])
    setup.drive.move_denied.add("loose")
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "conflict"
    assert result["conflict"]["code"] == "insufficient_permission" and result["conflict"]["operation"] == 1
    assert result["conflict"]["completed"]  # the folder creation already ran
    created = next(item for item in setup.drive.resources.values() if item.name == "Nueva")
    assert created.parents == ("dest",)


def test_apply_lets_a_rate_limit_propagate_so_repeating_resumes(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview([{"op": "move", "file_id": "loose", "parent_folder_id": "dest"}])

    def rate_limited(file_id, add_parent, remove_parents):
        raise HarnessError("drive_rate_limited", "límite", details={"http_status": 403})
    setup.drive.move = rate_limited
    with pytest.raises(HarnessError) as raised:
        setup.apply(plan["plan_id"])
    assert raised.value.code == "drive_rate_limited"
