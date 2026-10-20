from __future__ import annotations

from pathlib import Path

import pytest
from fakes import AtomicSharedState, FakeSheets, dossier_drive

from litman_harness.dossier.models import FOLDER_MIME, GOOGLE_SHEET_MIME, Resource
from litman_harness.dossier.service import ExpedienteService
from litman_harness.dossier.sheets import (SheetRange, SheetsService, matrix_sha256, normalized_matrix, parse_range,
                                           validated_operations)
from litman_harness.errors import HarnessError
from litman_harness.plans import PlanStore

PDF = "application/pdf"


class Setup:
    def __init__(self, tmp_path: Path, *, can_edit: bool = True):
        self.drive = dossier_drive()
        add = self.drive.add
        add(Resource("sheet", "Presupuesto", GOOGLE_SHEET_MIME, "1", drive_id="shared", parents=("root",),
                     capabilities={"canEdit": can_edit}))
        add(Resource("other-sheet", "Oferta técnica", PDF, "1", drive_id="shared", parents=("root",)), b"x")
        add(Resource("litman", "_LitMan", FOLDER_MIME, "1", drive_id="shared", parents=("root",)))
        add(Resource("litman-sheet", "Interno", GOOGLE_SHEET_MIME, "1", drive_id="shared", parents=("litman",),
                     capabilities={"canEdit": True}))
        add(Resource("outside", "Otra carpeta", FOLDER_MIME, "1", drive_id="shared"))
        add(Resource("outside-sheet", "Hoja ajena", GOOGLE_SHEET_MIME, "1", drive_id="shared", parents=("outside",),
                     capabilities={"canEdit": True}))
        self.sheets = FakeSheets()
        self.sheets.add("sheet", {"Hoja 1": [["Concepto", "Importe"], ["Grúas", 1200], ["Camiones", 300]],
                                  "Vacía": [], "Simple": [["antes"]]})
        self.sheets.add("litman-sheet", {"Hoja 1": [["x"]]})
        self.store = PlanStore(tmp_path / "plans")
        self.state = AtomicSharedState(self.drive)
        self.dossier = ExpedienteService(self.drive, self.store, self.state)
        self.service = SheetsService(self.dossier, self.sheets)

    def preview(self, operations):
        return self.service.preview_edit("root", "sheet", operations)

    def apply(self, plan_id):
        return self.service.apply_edit(plan_id)


def error(call) -> HarnessError:
    with pytest.raises(HarnessError) as raised:
        call()
    return raised.value


# -- range parsing and normalization ---------------------------------------------------------------

def test_parse_range_accepts_an_explicit_quoted_range():
    sheet_range = parse_range("'Hoja 1'!B2:C3")
    assert sheet_range == SheetRange("Hoja 1", 2, 2, 3, 3)
    assert sheet_range.rows == 2 and sheet_range.cols == 2
    assert sheet_range.a1 == "'Hoja 1'!B2:C3"


def test_parse_range_rejects_open_ended_forms():
    for value in ("Hoja 1!A:A", "Hoja 1!A1", "Hoja 1!1:1", "Hoja 1", "A1:B2", 3, None):
        assert error(lambda value=value: parse_range(value)).code == "invalid_request"


def test_parse_range_rejects_an_inverted_range():
    assert error(lambda: parse_range("Hoja!B2:A1")).code == "invalid_request"


def test_ranges_overlap_only_on_the_same_sheet_with_intersecting_bounds():
    base = SheetRange("Hoja 1", 1, 1, 2, 2)
    assert base.overlaps(SheetRange("Hoja 1", 2, 2, 3, 3))
    assert not base.overlaps(SheetRange("Hoja 1", 3, 1, 4, 2))
    assert not base.overlaps(SheetRange("Hoja 2", 1, 1, 2, 2))


def test_normalized_matrix_pads_and_canonicalizes_values():
    matrix = normalized_matrix([[None, "", 1200.0, True]], 2, 4)
    assert matrix == [["", "", 1200, True], ["", "", "", ""]]
    assert matrix_sha256(matrix) == matrix_sha256(normalized_matrix([[None, None, 1200, True]], 2, 4))


# -- shape validation --------------------------------------------------------------------------------

def test_validated_operations_rejects_bad_shapes():
    for operations in ([], [{}], [{"op": "update_range"}],
                       [{"op": "update_range", "range": "A", "values": [[1]], "extra": 1}],
                       [{"op": "update_range", "range": 3, "values": [[1]]}],
                       [{"op": "update_range", "range": "A", "values": []}],
                       [{"op": "update_range", "range": "A", "values": [[1], [1, 2]]}],
                       [{"op": "update_range", "range": "A", "values": [[{}]]}],
                       [{"op": "append_rows", "sheet": "", "values": [[1]]}],
                       [{"op": "other", "values": [[1]]}]):
        assert error(lambda operations=operations: validated_operations(operations)).code == "invalid_request"
    assert len(validated_operations([{"op": "update_range", "range": "A", "values": [[1]]}] * 20)) == 20
    assert error(lambda: validated_operations([{"op": "update_range", "range": "A", "values": [[1]]}] * 21)
                ).code == "invalid_request"


# -- preview -------------------------------------------------------------------------------------------

def test_preview_resolves_an_update_range_and_hashes_before_and_after(tmp_path: Path):
    setup = Setup(tmp_path)
    result = setup.preview([{"op": "update_range", "range": "'Hoja 1'!B2:B2", "values": [[1500]]}])
    assert result["spreadsheet_id"] == "sheet" and result["kind"] == "sheet_edit"
    action = setup.store.load(setup.dossier.account_id(), result["plan_id"]).actions[0]
    assert action.metadata["range"] == "'Hoja 1'!B2:B2" and action.metadata["values"] == [[1500]]
    assert action.metadata["before_sha256"] == matrix_sha256([[1200]])
    assert action.metadata["after_sha256"] == matrix_sha256([[1500]])
    assert result["operations"][0]["range"] == "'Hoja 1'!B2:B2"


def test_preview_resolves_append_rows_after_the_last_non_empty_row(tmp_path: Path):
    setup = Setup(tmp_path)
    result = setup.preview([{"op": "append_rows", "sheet": "Hoja 1", "values": [["Grúas", 500]]}])
    action = setup.store.load(setup.dossier.account_id(), result["plan_id"]).actions[0]
    assert action.metadata["range"] == "'Hoja 1'!A4:B4"


def test_preview_resolves_append_rows_into_an_empty_sheet_at_row_one(tmp_path: Path):
    setup = Setup(tmp_path)
    result = setup.preview([{"op": "append_rows", "sheet": "Vacía", "values": [["a"]]}])
    action = setup.store.load(setup.dossier.account_id(), result["plan_id"]).actions[0]
    assert action.metadata["range"] == "'Vacía'!A1:A1"


def test_preview_appends_after_a_formula_that_evaluates_to_empty(tmp_path: Path):
    setup = Setup(tmp_path)
    original_values = setup.sheets.values

    def values(spreadsheet_id, ranges, render):
        if ranges == ["'Vacía'"] and render == "FORMULA":
            return [{"range": "'Vacía'", "values": [["=IF(FALSE, 1, \"\")"]]}]
        return original_values(spreadsheet_id, ranges, render)

    setup.sheets.values = values
    result = setup.preview([{"op": "append_rows", "sheet": "Vacía", "values": [["a"]]}])
    action = setup.store.load(setup.dossier.account_id(), result["plan_id"]).actions[0]
    assert action.metadata["range"] == "'Vacía'!A2:A2"


def test_preview_stacks_two_appends_into_the_same_sheet_without_overlap(tmp_path: Path):
    setup = Setup(tmp_path)
    result = setup.preview([{"op": "append_rows", "sheet": "Hoja 1", "values": [["a"]]},
                            {"op": "append_rows", "sheet": "Hoja 1", "values": [["b"]]}])
    actions = setup.store.load(setup.dossier.account_id(), result["plan_id"]).actions
    assert actions[0].metadata["range"] == "'Hoja 1'!A4:A4"
    assert actions[1].metadata["range"] == "'Hoja 1'!A5:A5"


def test_preview_rejects_overlapping_ranges(tmp_path: Path):
    setup = Setup(tmp_path)
    exc = error(lambda: setup.preview([{"op": "update_range", "range": "'Hoja 1'!A1:B2", "values": [[1, 2], [3, 4]]},
                                       {"op": "update_range", "range": "'Hoja 1'!B2:C3",
                                        "values": [[5, 6], [7, 8]]}]))
    assert exc.code == "overlapping_operations" and exc.details["operations"] == [0, 1]


def test_preview_rejects_more_than_five_thousand_cells_in_total(tmp_path: Path):
    setup = Setup(tmp_path)
    exc = error(lambda: setup.preview([{"op": "update_range", "range": "'Hoja 1'!A1:ZZ100", "values": [
        [1] * 702 for _ in range(100)]}]))
    assert exc.code == "invalid_request"


def test_preview_rejects_an_unknown_sheet(tmp_path: Path):
    setup = Setup(tmp_path)
    for operation in ({"op": "update_range", "range": "'Nada'!A1:A1", "values": [[1]]},
                      {"op": "append_rows", "sheet": "Nada", "values": [[1]]}):
        exc = error(lambda operation=operation: setup.preview([operation]))
        assert exc.code == "invalid_request" and exc.details["sheet"] == "Nada"


def test_preview_rejects_values_that_do_not_match_the_range_size(tmp_path: Path):
    setup = Setup(tmp_path)
    exc = error(lambda: setup.preview([{"op": "update_range", "range": "'Hoja 1'!A1:B1", "values": [[1]]}]))
    assert exc.code == "invalid_request"


def test_preview_rejects_a_file_outside_the_tree_or_below_litman(tmp_path: Path):
    setup = Setup(tmp_path)
    assert error(lambda: setup.service.preview_edit(
        "root", "litman-sheet", [{"op": "update_range", "range": "'Hoja 1'!A1:A1", "values": [["x"]]}]
    )).code == "document_outside_tree"
    assert error(lambda: setup.service.preview_edit(
        "root", "outside-sheet", [{"op": "update_range", "range": "'Hoja 1'!A1:A1", "values": [["x"]]}]
    )).code == "document_outside_tree"


def test_preview_rejects_a_non_sheet_file(tmp_path: Path):
    setup = Setup(tmp_path)
    exc = error(lambda: setup.service.preview_edit(
        "root", "other-sheet", [{"op": "update_range", "range": "'Hoja 1'!A1:A1", "values": [["x"]]}]))
    assert exc.code == "unsupported_document"


def test_preview_rejects_when_the_account_cannot_edit(tmp_path: Path):
    setup = Setup(tmp_path, can_edit=False)
    exc = error(lambda: setup.preview([{"op": "update_range", "range": "'Hoja 1'!A1:A1", "values": [["x"]]}]))
    assert exc.code == "insufficient_capability"


# -- apply ---------------------------------------------------------------------------------------------

def test_apply_writes_the_accepted_range_with_raw_values(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview([{"op": "update_range", "range": "'Hoja 1'!B2:B2", "values": [[1500]]}])
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded" and result["writes"] is True
    assert setup.sheets.updates == [("sheet", "'Hoja 1'!B2:B2", [[1500]])]
    assert setup.sheets.spreadsheets["sheet"]["Hoja 1"][1][1] == 1500


def test_apply_writes_every_action_of_a_multi_operation_plan(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview([{"op": "update_range", "range": "'Hoja 1'!B2:B2", "values": [[1500]]},
                          {"op": "append_rows", "sheet": "Hoja 1", "values": [["Grúas", 500]]}])
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded"
    assert len(setup.sheets.updates) == 2
    assert setup.sheets.spreadsheets["sheet"]["Hoja 1"][3] == ["Grúas", 500]


def test_apply_completes_without_writing_when_the_range_already_has_the_expected_values(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview([{"op": "update_range", "range": "'Hoja 1'!B2:B2", "values": [[1500]]}])
    setup.sheets.spreadsheets["sheet"]["Hoja 1"][1][1] = 1500  # the write already happened; the answer was lost
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded" and setup.sheets.updates == []


def test_apply_matches_a_canonical_unquoted_range_from_the_sheets_api(tmp_path: Path):
    setup = Setup(tmp_path)
    original_values = setup.sheets.values

    def values(spreadsheet_id, ranges, render):
        result = original_values(spreadsheet_id, ranges, render)
        for entry in result:
            entry["range"] = entry["range"].replace("'Simple'", "Simple")
        return result

    setup.sheets.values = values
    plan = setup.preview([{"op": "update_range", "range": "'Simple'!A1:A1", "values": [["después"]]}])
    setup.sheets.spreadsheets["sheet"]["Simple"][0][0] = "después"
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded" and setup.sheets.updates == []


def test_apply_returns_a_sheet_changed_conflict_without_writing(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview([{"op": "update_range", "range": "'Hoja 1'!B2:B2", "values": [[1500]]}])
    setup.sheets.spreadsheets["sheet"]["Hoja 1"][1][1] = 9999  # someone else's edit between preview and apply
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "conflict" and result["conflict"]["code"] == "sheet_changed"
    assert setup.sheets.updates == [] and setup.sheets.spreadsheets["sheet"]["Hoja 1"][1][1] == 9999


def test_apply_leaves_earlier_actions_written_when_a_later_one_conflicts(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview([{"op": "update_range", "range": "'Hoja 1'!B2:B2", "values": [[1500]]},
                          {"op": "update_range", "range": "'Hoja 1'!B3:B3", "values": [[400]]}])
    setup.sheets.spreadsheets["sheet"]["Hoja 1"][2][1] = 9999
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "conflict" and result["completed_actions"]
    assert setup.sheets.spreadsheets["sheet"]["Hoja 1"][1][1] == 1500


def test_apply_rejects_when_the_account_can_no_longer_edit(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview([{"op": "update_range", "range": "'Hoja 1'!B2:B2", "values": [[1500]]}])
    setup.drive.add(Resource("sheet", "Presupuesto", GOOGLE_SHEET_MIME, "1", drive_id="shared", parents=("root",),
                             capabilities={"canEdit": False}))
    assert error(lambda: setup.apply(plan["plan_id"])).code == "insufficient_capability"


def test_apply_rechecks_can_edit_before_each_action_of_a_multi_operation_plan(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview([{"op": "update_range", "range": "'Hoja 1'!B2:B2", "values": [[1500]]},
                          {"op": "update_range", "range": "'Hoja 1'!B3:B3", "values": [[400]]}])
    original_update = setup.sheets.update

    def update(spreadsheet_id, a1_range, values):
        original_update(spreadsheet_id, a1_range, values)
        setup.drive.add(Resource("sheet", "Presupuesto", GOOGLE_SHEET_MIME, "1", drive_id="shared",
                                 parents=("root",), capabilities={"canEdit": False}))

    setup.sheets.update = update
    exc = error(lambda: setup.apply(plan["plan_id"]))
    assert exc.code == "insufficient_capability"
    assert setup.sheets.updates == [("sheet", "'Hoja 1'!B2:B2", [[1500]])]
    assert setup.sheets.spreadsheets["sheet"]["Hoja 1"][2][1] != 400


def test_apply_replays_a_succeeded_plan_without_writing_again(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview([{"op": "update_range", "range": "'Hoja 1'!B2:B2", "values": [[1500]]}])
    setup.apply(plan["plan_id"])
    result = setup.apply(plan["plan_id"])
    assert result["replayed"] is True and len(setup.sheets.updates) == 1
