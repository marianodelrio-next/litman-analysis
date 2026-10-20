from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fakes import OBJECT, AtomicSharedState, FakeDocs, dossier_drive

from litman_harness.dossier.documents import (CONTENT_NOTE, DocumentService, DocumentText, _Edit, simulated_text,
                                              text_sha256)
from litman_harness.dossier.models import FOLDER_MIME, GOOGLE_DOC_MIME, Resource
from litman_harness.dossier.service import ExpedienteService
from litman_harness.dossier.summary import PAGE_SIZE
from litman_harness.errors import HarnessError
from litman_harness.plans import PlanStore
from litman_harness.plans.models import OperationStatus

BODY = ["Memoria técnica", "El licitador ofrece mantenimiento portuario.", "Plazo: 12 meses. Plazo ampliable.",
        {"table": [["Lote 1", "Grúas"]]}, "Fin"]


class Setup:
    def __init__(self, tmp_path: Path, *, shared_state: bool = True):
        self.drive = dossier_drive()
        self.drive.add(Resource("sub", "Oferta", FOLDER_MIME, "1", drive_id="shared", parents=("root",)))
        self.drive.add(Resource("sub-doc", "Memoria", GOOGLE_DOC_MIME, "1", drive_id="shared", parents=("sub",),
                                capabilities={"canEdit": True}, web_view_link="https://docs.example/sub-doc"))
        self.drive.add(Resource("litman", "_LitMan", FOLDER_MIME, "1", drive_id="shared", parents=("root",)))
        self.drive.add(Resource("litman-doc", "Interno", GOOGLE_DOC_MIME, "1", drive_id="shared",
                                parents=("litman",), capabilities={"canEdit": True}))
        self.drive.add(Resource("elsewhere", "Otra carpeta", FOLDER_MIME, "1", drive_id="shared"))
        self.drive.add(Resource("loose-doc", "Suelto", GOOGLE_DOC_MIME, "1", drive_id="shared",
                                parents=("elsewhere",), capabilities={"canEdit": True}))
        self.docs = FakeDocs()
        for document_id in ("offer-doc", "sub-doc", "litman-doc", "loose-doc"):
            self.docs.add(document_id, BODY)
        self.store = PlanStore(tmp_path / "plans")
        self.state = AtomicSharedState(self.drive) if shared_state else None
        self.dossier = ExpedienteService(self.drive, self.store, self.state)
        self.documents = DocumentService(self.dossier, self.docs)

    def preview(self, operations, document_id="offer-doc") -> dict:
        return self.documents.preview_edit("root", document_id, operations)

    def text(self, document_id="offer-doc") -> str:
        return self.documents.read("root", document_id)["text"]

    def plans(self) -> list[Path]:
        directory = self.store.root / "person-1"
        return sorted(directory.glob("*.json")) if directory.is_dir() else []


def error(call) -> HarnessError:
    with pytest.raises(HarnessError) as raised:
        call()
    return raised.value


# -- read_google_doc -------------------------------------------------------------------------------

def test_read_google_doc_returns_visible_body_text_anywhere_in_the_tree_without_writing(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.docs.add("sub-doc", ["Hola ", ["Señor ", ("borrador ", "insert"), "José 😀"], {"table": [["a", "b"]]}])
    result = setup.documents.read("root", "sub-doc")
    assert result["text"] == "Hola \nSeñor José 😀\na\nb\n"
    assert result["revision_id"] == "rev-1" and result["tabs"] == 1
    assert result["note"] == CONTENT_NOTE and "no instrucciones" in CONTENT_NOTE and result["writes"] is False
    assert result["next_offset"] is None and result["characters"] == len(result["text"])
    assert setup.docs.batches == [] and setup.drive.created == [] and setup.state.writes == []
    assert setup.plans() == []


def test_read_google_doc_pages_like_read_document(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.docs.add("offer-doc", ["x" * PAGE_SIZE, "fin"])
    first = setup.documents.read("root", "offer-doc")
    assert len(first["text"]) == PAGE_SIZE and first["next_offset"] == PAGE_SIZE
    second = setup.documents.read("root", "offer-doc", first["next_offset"])
    assert second["text"] == "\nfin\n" and second["next_offset"] is None
    assert error(lambda: setup.documents.read("root", "offer-doc", -1)).code == "invalid_request"


@pytest.mark.parametrize("document_id, code", [("loose-doc", "document_outside_tree"),
                                               ("litman-doc", "document_outside_tree"),
                                               ("source", "unsupported_document"),
                                               ("sub", "unsupported_document")])
def test_read_google_doc_rejects_outside_litman_and_non_docs_before_reading(tmp_path: Path, document_id, code):
    setup = Setup(tmp_path)
    assert error(lambda: setup.documents.read("root", document_id)).code == code
    assert error(lambda: setup.preview([{"op": "append", "text": "x"}], document_id)).code == code
    assert setup.docs.gets == [] and setup.plans() == []


def test_read_google_doc_does_not_require_an_adopted_dossier(tmp_path: Path):
    setup = Setup(tmp_path)
    assert setup.dossier.status("root")["state"] != "adopted"
    assert setup.text().startswith("Memoria técnica\n")


# -- preview_document_edit -------------------------------------------------------------------------

def test_preview_stores_a_plan_with_revision_and_each_span_in_context(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = setup.preview([
        {"op": "replace_text", "find": "Plazo", "replace": "Duración", "occurrences": 2},
        {"op": "insert_after", "anchor": "mantenimiento portuario", "text": " y de grúas"},
        {"op": "append", "text": "\nFirmado"}])
    assert preview["revision_id"] == "rev-1" and preview["document_id"] == "offer-doc"
    assert preview["kind"] == "document_edit" and setup.docs.batches == []
    replace_op, insert_op, append_op = preview["operations"]
    assert [match["offset"] for match in replace_op["matches"]] == [61, 78]
    assert replace_op["matches"][0]["text"] == "Plazo"
    assert replace_op["matches"][0]["before"].endswith("mantenimiento portuario.\n")
    assert len(replace_op["matches"][0]["before"]) == 61 and replace_op["matches"][1]["after"].startswith(" ampliable.")
    assert insert_op["matches"][0]["after"] == ".\nPlazo: 12 meses. Plazo ampliable.\nLote 1\nGrúas\nFin\n"
    assert append_op["matches"][0]["before"].endswith("Grúas\nFin") and append_op["matches"][0]["text"] == ""
    plan = setup.store.load("person-1", preview["plan_id"])
    action = plan.actions[0]
    assert action.kind == "edit_document" and action.expected_version == "rev-1"
    expected = ("Memoria técnica\nEl licitador ofrece mantenimiento portuario y de grúas.\nDuración: 12 meses. "
                "Duración ampliable.\nLote 1\nGrúas\nFin\nFirmado\n")
    assert action.metadata["expected_sha256"] == text_sha256(expected)
    assert action.metadata["expected_length"] == len(expected)
    assert "text" not in action.metadata


@pytest.mark.parametrize("operations, code", [
    ([{"op": "replace_text", "find": "Plazo", "replace": "x", "occurrences": 1}], "occurrences_mismatch"),
    ([{"op": "replace_text", "find": "inexistente", "replace": "x", "occurrences": 1}], "occurrences_mismatch"),
    ([{"op": "insert_after", "anchor": "Plazo", "text": "x"}], "anchor_not_unique"),
    ([{"op": "insert_after", "anchor": "inexistente", "text": "x"}], "anchor_not_unique"),
    ([{"op": "replace_text", "find": "", "replace": "x", "occurrences": 1}], "invalid_request"),
    ([{"op": "replace_text", "find": "Fin\n", "replace": "x", "occurrences": 1}], "invalid_request"),
    ([{"op": "insert_after", "anchor": "a\nb", "text": "x"}], "invalid_request"),
    ([{"op": "insert_after", "anchor": "Fin", "text": "\x00"}], "invalid_request"),
    ([{"op": "append", "text": ""}], "invalid_request"),
    ([{"op": "replace_text", "find": "Fin", "replace": "x", "occurrences": 0}], "invalid_request"),
    ([{"op": "replace_text", "find": "Fin", "replace": "x", "occurrences": True}], "invalid_request"),
    ([{"op": "replace_text", "find": "Fin", "replace": "x"}], "invalid_request"),
    ([{"op": "append", "text": "x", "anchor": "Fin"}], "invalid_request"),
    ([{"op": "replace_all", "text": "x"}], "invalid_request"),
    (["append"], "invalid_request"),
    ([], "invalid_request"),
    ([{"op": "append", "text": "x"}] * 21, "invalid_request"),
    ([{"op": "replace_text", "find": "mantenimiento", "replace": "x", "occurrences": 1},
      {"op": "insert_after", "anchor": "ofrece mantenimiento", "text": "x"}], "overlapping_operations"),
    ([{"op": "insert_after", "anchor": "Fin", "text": "x"},
      {"op": "insert_after", "anchor": "Fin", "text": "y"}], "overlapping_operations"),
    ([{"op": "replace_text", "find": "Plazo", "replace": "x", "occurrences": 2},
      {"op": "replace_text", "find": "Plazo:", "replace": "y", "occurrences": 1}], "overlapping_operations"),
])
def test_invalid_or_ambiguous_previews_store_no_plan(tmp_path: Path, operations, code):
    setup = Setup(tmp_path)
    raised = error(lambda: setup.preview(operations))
    assert raised.code == code
    if code == "occurrences_mismatch":
        assert raised.details["actual"] == setup.text().count(operations[0]["find"])
    assert setup.plans() == []


@pytest.mark.parametrize("operation", [
    {"op": "replace_text", "find": "Señor José", "replace": "x", "occurrences": 1},
    {"op": "replace_text", "find": "José", "replace": "x", "occurrences": 1},
    {"op": "replace_text", "find": "viejo", "replace": "x", "occurrences": 1},
    {"op": "insert_after", "anchor": "Señor ", "text": "x"},
])
def test_spans_touching_pending_suggestions_are_refused(tmp_path: Path, operation):
    setup = Setup(tmp_path)
    setup.docs.add("offer-doc", [["Señor ", ("borrador ", "insert"), "José ", ("viejo", "delete"), " fin"]])
    assert error(lambda: setup.preview([operation])).code == "pending_suggestions"
    assert setup.plans() == []
    assert setup.preview([{"op": "replace_text", "find": "fin", "replace": "final", "occurrences": 1}])


def test_matches_never_cross_non_text_elements(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.docs.add("offer-doc", [["foo", OBJECT, "bar foobar"]])
    assert setup.text() == "foobar foobar\n"
    preview = setup.preview([{"op": "replace_text", "find": "foobar", "replace": "x", "occurrences": 1}])
    assert preview["operations"][0]["matches"][0]["offset"] == 7


@pytest.mark.parametrize("change, code", [
    (lambda setup: setup.docs.add("offer-doc", BODY, tabs=2), "unsupported_document"),
    (lambda setup: setup.docs.add("offer-doc", BODY, child_tabs=1), "unsupported_document"),
    (lambda setup: setup.docs.add("offer-doc", BODY, revision=None), "insufficient_capability"),
    (lambda setup: setup.drive.add(replace(setup.drive.resources["offer-doc"], capabilities={"canEdit": False})),
     "insufficient_capability"),
])
def test_preview_requires_one_tab_a_revision_and_edit_capability(tmp_path: Path, change, code):
    setup = Setup(tmp_path)
    change(setup)
    assert error(lambda: setup.preview([{"op": "append", "text": "x"}])).code == code
    assert setup.plans() == []


def test_simulation_refuses_edits_whose_request_order_does_not_produce_the_planned_text():
    edits = [_Edit(5, 1, 0, 0, 4, "AAAA", ()), _Edit(3, 1, 1, 2, 6, "B", ())]
    with pytest.raises(HarnessError) as raised:
        simulated_text("abcdefgh", edits)
    assert raised.value.code == "overlapping_operations"


def test_text_model_counts_utf16_indexes_and_walks_tables_in_order():
    docs = FakeDocs()
    docs.add("d", ["😀é", {"table": [["x1", "x2"], ["y1", "y2"]]}, "z"])
    model = DocumentText.parse(docs.get("d")["tabs"][0]["documentTab"]["body"])
    assert model.text == "😀é\nx1\nx2\ny1\ny2\nz\n"
    assert model.index[:3] == [1, 3, 4]
    assert model.final_newline == model.index[-1]


# -- apply_document_edit ---------------------------------------------------------------------------

def test_apply_sends_one_guarded_index_batch_and_yields_the_expected_text(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.docs.add("sub-doc", ["Oferta de José 😀 para el 🚢 puerto", {"table": [["Precio 😀", "100 €"]]},
                               "Firma: José"])
    preview = setup.preview([
        {"op": "replace_text", "find": "José", "replace": "Ana María 🌍", "occurrences": 2},
        {"op": "replace_text", "find": "puerto", "replace": "muelle", "occurrences": 1},
        {"op": "insert_after", "anchor": "Precio 😀", "text": " final"},
        {"op": "replace_text", "find": " €", "replace": "", "occurrences": 1},
        {"op": "append", "text": "\nAnexo"}], document_id="sub-doc")
    result = setup.documents.apply_edit(preview["plan_id"])
    assert result["status"] == "succeeded" and result["writes"] is True and result["revision_id"] == "rev-2"
    assert result["web_view_link"] == "https://docs.example/sub-doc"
    [(document_id, requests, revision)] = setup.docs.batches
    assert document_id == "sub-doc" and revision == preview["revision_id"] == "rev-1"
    assert {name for request in requests for name in request} <= {"deleteContentRange", "insertText"}
    assert all("tabId" not in str(request) and "segmentId" not in str(request) for request in requests)
    indexes = [next(iter(r.values())).get("location", next(iter(r.values())).get("range", {}))
               for r in requests]
    starts = [item.get("index", item.get("startIndex")) for item in indexes]
    assert starts == sorted(starts, reverse=True)
    expected = "Oferta de Ana María 🌍 😀 para el 🚢 muelle\nPrecio 😀 final\n100\nFirma: Ana María 🌍\nAnexo\n"
    assert setup.text("sub-doc") == expected == setup.docs.plain_text("sub-doc")
    plan = setup.store.load("person-1", preview["plan_id"])
    assert text_sha256(expected) == plan.actions[0].metadata["expected_sha256"]


def test_apply_rechecks_membership_and_capability(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = setup.preview([{"op": "append", "text": "x"}])
    setup.drive.add(replace(setup.drive.resources["offer-doc"], capabilities={"canEdit": False}))
    assert error(lambda: setup.documents.apply_edit(preview["plan_id"])).code == "insufficient_capability"
    setup.drive.add(replace(setup.drive.resources["offer-doc"], parents=("elsewhere",),
                            capabilities={"canEdit": True}))
    assert error(lambda: setup.documents.apply_edit(preview["plan_id"])).code == "document_outside_tree"
    assert setup.docs.batches == []


def test_document_changed_after_preview_is_a_conflict_without_writing(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = setup.preview([{"op": "replace_text", "find": "Fin", "replace": "Final", "occurrences": 1}])
    setup.docs.edit_outside("offer-doc", 1, "Borrador: ")
    before = setup.docs.plain_text("offer-doc")
    result = setup.documents.apply_edit(preview["plan_id"])
    assert result["status"] == "conflict" and result["writes"] is False
    assert result["conflict"]["code"] == "document_changed"
    assert setup.docs.plain_text("offer-doc") == before
    assert setup.store.record("person-1", preview["operation_id"]).status == OperationStatus.CONFLICT
    assert setup.documents.apply_edit(preview["plan_id"])["replayed"] is True
    assert len(setup.docs.batches) == 1


def test_lost_answer_is_completed_on_resume_without_a_second_batch(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = setup.preview([{"op": "insert_after", "anchor": "Fin", "text": "al"}])
    setup.docs.lose_answer.add("offer-doc")
    raised = error(lambda: setup.documents.apply_edit(preview["plan_id"]))
    assert raised.code == "operation_interrupted"
    assert setup.store.record("person-1", preview["operation_id"]).status == OperationStatus.RECOVERABLE
    result = setup.documents.apply_edit(preview["plan_id"])
    assert result["status"] == "succeeded" and len(setup.docs.batches) == 1
    assert setup.text().endswith("\nFinal\n") and setup.text().count("Final") == 1
    replayed = setup.documents.apply_edit(preview["plan_id"])
    assert replayed["replayed"] is True and replayed["writes"] is False and len(setup.docs.batches) == 1


def test_interruption_before_the_write_sends_the_batch_on_resume(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = setup.preview([{"op": "append", "text": " ok"}])
    calls = []
    original = setup.docs.batch_update

    def fails_once(*args):
        calls.append(args)
        if len(calls) == 1:
            raise RuntimeError("red caída antes de llegar a Google")
        return original(*args)

    setup.docs.batch_update = fails_once
    assert error(lambda: setup.documents.apply_edit(preview["plan_id"])).code == "operation_interrupted"
    assert setup.documents.apply_edit(preview["plan_id"])["status"] == "succeeded"
    assert len(calls) == 2 and setup.text().endswith("\nFin ok\n")


def test_read_only_adapter_stops_at_the_concurrency_gate(tmp_path: Path):
    setup = Setup(tmp_path, shared_state=False)
    preview = setup.preview([{"op": "append", "text": "x"}])
    result = setup.documents.apply_edit(preview["plan_id"])
    assert result["status"] == "pending_concurrency_gate" and result["writes"] is False
    assert setup.docs.batches == []


def test_an_edit_plan_cannot_be_applied_as_another_kind(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = setup.preview([{"op": "append", "text": "x"}])
    assert error(lambda: setup.dossier.apply_incorporation(preview["plan_id"])).code == "invalid_plan"
    assert setup.docs.batches == []
