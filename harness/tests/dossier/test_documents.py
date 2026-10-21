from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fakes import OBJECT, AtomicSharedState, FakeDocs, dossier_drive, minimal_docx

from litman_harness.adapters.documents import DOCX_MIME
from litman_harness.dossier.documents import (CONTENT_NOTE, DocumentService, DocumentText, _Edit, simulated_text,
                                              text_sha256)
from litman_harness.dossier.models import FOLDER_MIME, GOOGLE_DOC_MIME, Resource
from litman_harness.dossier.service import ExpedienteService
from litman_harness.dossier.summary import PAGE_SIZE
from litman_harness.errors import HarnessError
from litman_harness.plans import PlanStore
from litman_harness.plans.models import OperationStatus

DOCX = minimal_docx("Memoria técnica", ("Lote 1", "Grúas"))
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
        self.drive.add(Resource("litman-sub", "Borradores", FOLDER_MIME, "1", drive_id="shared", parents=("litman",)))
        self.drive.add(Resource("memoria-docx", "memoria.docx", DOCX_MIME, "1", drive_id="shared", parents=("sub",)),
                       DOCX)
        self.drive.add(Resource("litman-docx", "interno.docx", DOCX_MIME, "1", drive_id="shared",
                                parents=("litman",)), DOCX)
        self.drive.add(Resource("loose-docx", "suelto.docx", DOCX_MIME, "1", drive_id="shared",
                                parents=("elsewhere",)), DOCX)
        self.docs = FakeDocs()
        for document_id in ("offer-doc", "sub-doc", "litman-doc", "loose-doc"):
            self.docs.add(document_id, BODY)
        self.drive.docs = self.docs
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


# -- style operations ------------------------------------------------------------------------------

STYLES = [
    {"op": "set_paragraph_style", "anchor": "Memoria técnica", "style": "HEADING_1"},
    {"op": "set_text_style", "find": "Plazo", "occurrences": 2, "bold": True},
    {"op": "set_list", "anchor": "Grúas", "list": "bullets"}]


def test_style_preview_stores_index_based_requests_and_the_unchanged_text_hash(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = setup.preview([
        {"op": "set_paragraph_style", "anchor": "mantenimiento", "style": "TITLE"},
        {"op": "set_text_style", "find": "Plazo", "occurrences": 2, "bold": True, "italic": False},
        {"op": "set_list", "anchor": "Fin", "list": "numbered"}])
    assert preview["kind"] == "document_edit" and setup.docs.batches == [] and len(setup.plans()) == 1
    paragraph_op, text_op, list_op = preview["operations"]
    assert paragraph_op["matches"][0]["text"] == "mantenimiento"
    assert paragraph_op["paragraph"] == "El licitador ofrece mantenimiento portuario."
    assert [match["offset"] for match in text_op["matches"]] == [61, 78]
    assert list_op["paragraph"] == "Fin"
    action = setup.store.load("person-1", preview["plan_id"]).actions[0]
    assert action.expected_version == "rev-1" and action.metadata["style_only"] is True
    assert action.metadata["expected_sha256"] == text_sha256(setup.text())
    assert action.metadata["expected_length"] == len(setup.text())
    by_name = {name: body for request in action.metadata["requests"] for name, body in request.items()}
    assert by_name["updateParagraphStyle"] == {"range": {"startIndex": 17, "endIndex": 62},
                                               "paragraphStyle": {"namedStyleType": "TITLE"},
                                               "fields": "namedStyleType"}
    assert by_name["createParagraphBullets"]["bulletPreset"] == "NUMBERED_DECIMAL_ALPHA_ROMAN"
    text_requests = [r["updateTextStyle"] for r in action.metadata["requests"] if "updateTextStyle" in r]
    assert len(text_requests) == 2 and all(r["fields"] == "bold,italic" for r in text_requests)
    assert all(r["textStyle"] == {"bold": True, "italic": False} for r in text_requests)


def test_apply_formats_paragraphs_text_and_lists_with_one_guarded_batch_and_no_text_change(tmp_path: Path):
    setup = Setup(tmp_path)
    before = setup.text()
    preview = setup.preview([*STYLES, {"op": "set_list", "anchor": "Fin", "list": "none"},
                             {"op": "set_text_style", "find": "ofrece", "occurrences": 1, "underline": True}])
    result = setup.documents.apply_edit(preview["plan_id"])
    assert result["status"] == "succeeded" and result["writes"] is True and result["revision_id"] == "rev-2"
    [(document_id, requests, revision)] = setup.docs.batches
    assert document_id == "offer-doc" and revision == preview["revision_id"] == "rev-1"
    assert {name for request in requests for name in request} == {
        "updateParagraphStyle", "updateTextStyle", "createParagraphBullets", "deleteParagraphBullets"}
    assert setup.text() == before
    assert setup.docs.paragraph_style("offer-doc", "Memoria técnica") == ("HEADING_1", "none")
    assert setup.docs.paragraph_style("offer-doc", "Grúas") == ("NORMAL_TEXT", "bullets")
    assert setup.docs.paragraph_style("offer-doc", "Fin") == ("NORMAL_TEXT", "none")
    assert setup.docs.paragraph_style("offer-doc", "El licitador ofrece mantenimiento portuario.") == (
        "NORMAL_TEXT", "none")
    assert setup.docs.text_style("offer-doc", "ofrece") == {"underline": True}
    assert setup.docs.text_style("offer-doc", "licitador") == {}
    assert [setup.docs.text_style("offer-doc", "Plazo", nth) for nth in (0, 1)] == [{"bold": True}] * 2
    assert setup.docs.text_style("offer-doc", "ampliable") == {}


def test_text_style_only_touches_the_given_flags(tmp_path: Path):
    setup = Setup(tmp_path)
    first = setup.preview([{"op": "set_text_style", "find": "Fin", "occurrences": 1, "bold": True, "italic": True}])
    setup.documents.apply_edit(first["plan_id"])
    second = setup.preview([{"op": "set_text_style", "find": "Fin", "occurrences": 1, "italic": False}])
    setup.documents.apply_edit(second["plan_id"])
    assert setup.docs.batches[1][1][0]["updateTextStyle"]["fields"] == "italic"
    assert setup.docs.text_style("offer-doc", "Fin") == {"bold": True, "italic": False}


@pytest.mark.parametrize("operations, code", [
    ([{"op": "set_paragraph_style", "anchor": "Fin", "style": "HEADING_4"}], "invalid_request"),
    ([{"op": "set_paragraph_style", "anchor": "Fin", "style": "heading_1"}], "invalid_request"),
    ([{"op": "set_paragraph_style", "anchor": "Fin"}], "invalid_request"),
    ([{"op": "set_paragraph_style", "anchor": "a\nb", "style": "TITLE"}], "invalid_request"),
    ([{"op": "set_text_style", "find": "Fin", "occurrences": 1}], "invalid_request"),
    ([{"op": "set_text_style", "find": "Fin", "occurrences": 1, "bold": "yes"}], "invalid_request"),
    ([{"op": "set_text_style", "find": "Fin", "occurrences": 1, "bold": 1}], "invalid_request"),
    ([{"op": "set_text_style", "find": "Fin", "occurrences": 1, "color": True}], "invalid_request"),
    ([{"op": "set_text_style", "find": "Fin", "bold": True}], "invalid_request"),
    ([{"op": "set_list", "anchor": "Fin", "list": "roman"}], "invalid_request"),
    ([{"op": "set_list", "anchor": "Fin", "list": "bullets", "text": "x"}], "invalid_request"),
    ([{"op": "set_text_style", "find": "Plazo", "occurrences": 1, "bold": True}], "occurrences_mismatch"),
    ([{"op": "set_text_style", "find": "inexistente", "occurrences": 1, "bold": True}], "occurrences_mismatch"),
    ([{"op": "set_paragraph_style", "anchor": "Plazo", "style": "TITLE"}], "anchor_not_unique"),
    ([{"op": "set_list", "anchor": "inexistente", "list": "bullets"}], "anchor_not_unique"),
    ([{"op": "set_paragraph_style", "anchor": "Fin", "style": "TITLE"},
      {"op": "set_paragraph_style", "anchor": "Fin", "style": "SUBTITLE"}], "overlapping_operations"),
    ([{"op": "set_list", "anchor": "Memoria", "list": "bullets"},
      {"op": "set_list", "anchor": "técnica", "list": "none"}], "overlapping_operations"),
    ([{"op": "set_text_style", "find": "Plazo", "occurrences": 2, "bold": True},
      {"op": "set_text_style", "find": "Plazo:", "occurrences": 1, "italic": True}], "overlapping_operations"),
    ([{"op": "set_paragraph_style", "anchor": "Fin", "style": "TITLE"},
      {"op": "append", "text": "x"}], "mixed_operations"),
    ([{"op": "replace_text", "find": "Fin", "replace": "x", "occurrences": 1},
      {"op": "set_text_style", "find": "Grúas", "occurrences": 1, "bold": True}], "mixed_operations"),
])
def test_invalid_style_previews_store_no_plan(tmp_path: Path, operations, code):
    setup = Setup(tmp_path)
    assert error(lambda: setup.preview(operations)).code == code
    assert setup.plans() == [] and setup.docs.batches == []


def test_style_operations_on_different_properties_of_one_paragraph_are_allowed(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = setup.preview([{"op": "set_paragraph_style", "anchor": "Fin", "style": "HEADING_2"},
                             {"op": "set_list", "anchor": "Fin", "list": "bullets"},
                             {"op": "set_text_style", "find": "Fin", "occurrences": 1, "bold": True}])
    setup.documents.apply_edit(preview["plan_id"])
    assert setup.docs.paragraph_style("offer-doc", "Fin") == ("HEADING_2", "bullets")


@pytest.mark.parametrize("kind", ["bullets", "numbered", "none"])
def test_set_list_refuses_a_paragraph_that_starts_with_a_tab(tmp_path: Path, kind):
    setup = Setup(tmp_path)
    setup.docs.add("offer-doc", ["\tsangrado", "normal"])
    assert error(lambda: setup.preview([{"op": "set_list", "anchor": "sangrado", "list": kind}])
                 ).code == "unsupported_document"
    assert setup.plans() == []
    assert setup.preview([{"op": "set_list", "anchor": "normal", "list": kind}])
    assert setup.preview([{"op": "set_paragraph_style", "anchor": "sangrado", "style": "TITLE"}])


def test_style_spans_touching_pending_suggestions_are_refused(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.docs.add("offer-doc", [["Señor ", ("borrador ", "insert"), "José"]])
    assert error(lambda: setup.preview([{"op": "set_text_style", "find": "José", "occurrences": 1, "bold": True}])
                 ).code == "pending_suggestions"


def test_style_paragraphs_inside_a_table_cell_are_styled(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = setup.preview([{"op": "set_paragraph_style", "anchor": "Grúas", "style": "SUBTITLE"}])
    setup.documents.apply_edit(preview["plan_id"])
    assert setup.docs.paragraph_style("offer-doc", "Grúas") == ("SUBTITLE", "none")
    assert setup.docs.paragraph_style("offer-doc", "Lote 1") == ("NORMAL_TEXT", "none")


def test_style_apply_rechecks_membership_and_a_changed_document_is_a_conflict(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = setup.preview(STYLES)
    setup.docs.edit_outside("offer-doc", 1, "Nuevo ")
    result = setup.documents.apply_edit(preview["plan_id"])
    assert result["status"] == "conflict" and result["conflict"]["code"] == "document_changed"
    assert result["writes"] is False and setup.text().startswith("Nuevo Memoria")


def test_style_plan_whose_answer_was_lost_is_completed_from_the_styles_read_back_without_a_second_batch(
        tmp_path: Path):
    setup = Setup(tmp_path)
    preview = setup.preview([{"op": "set_paragraph_style", "anchor": "Fin", "style": "HEADING_3"},
                             {"op": "set_text_style", "find": "Fin", "occurrences": 1, "bold": True,
                              "highlight_color": "#ffff00", "link_url": "https://example.org/fin"}])
    setup.docs.lose_answer.add("offer-doc")
    assert error(lambda: setup.documents.apply_edit(preview["plan_id"])).code == "operation_interrupted"
    assert setup.docs.documents["offer-doc"]["revision"] == "rev-2"
    result = setup.documents.apply_edit(preview["plan_id"])
    assert result["status"] == "succeeded" and result["revision_id"] == "rev-2"
    assert setup.store.record("person-1", preview["operation_id"]).status == OperationStatus.SUCCEEDED
    assert [batch[2] for batch in setup.docs.batches] == ["rev-1"]
    assert setup.docs.paragraph_style("offer-doc", "Fin") == ("HEADING_3", "none")
    assert setup.docs.text_style("offer-doc", "Fin") == {"bold": True, "background": "#FFFF00",
                                                         "link": "https://example.org/fin"}
    replayed = setup.documents.apply_edit(preview["plan_id"])
    assert replayed["replayed"] is True and len(setup.docs.batches) == 1


def test_style_plan_interrupted_before_the_write_is_resent_on_the_preview_revision(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = setup.preview([{"op": "set_text_style", "find": "Fin", "occurrences": 1, "highlight_color": "#00FF00"}])
    calls = []
    original = setup.docs.batch_update

    def fails_once(*args):
        calls.append(args)
        if len(calls) == 1:
            raise RuntimeError("red caída antes de llegar a Google")
        return original(*args)

    setup.docs.batch_update = fails_once
    assert error(lambda: setup.documents.apply_edit(preview["plan_id"])).code == "operation_interrupted"
    result = setup.documents.apply_edit(preview["plan_id"])
    assert result["status"] == "succeeded" and [call[2] for call in calls] == ["rev-1", "rev-1"]
    assert setup.docs.text_style("offer-doc", "Fin") == {"background": "#00FF00"}


@pytest.mark.parametrize("change", [
    {"background": "#FF0000"},  # someone highlighted the text in another color
    {"link": "https://otro.example/"},  # someone linked it elsewhere
    {"italic": True},  # a property the plan does not set: the revision still moved
])
def test_style_plan_not_written_whose_document_then_changed_format_only_is_a_conflict_without_resending(
        tmp_path: Path, change):
    setup = Setup(tmp_path)
    before = setup.text()
    preview = setup.preview([{"op": "set_text_style", "find": "Fin", "occurrences": 1, "highlight_color": "#FFFF00",
                              "link_url": "https://example.org/"}])
    original = setup.docs.batch_update

    def lost_before_writing(*args):
        setup.docs.batch_update = original
        raise RuntimeError("respuesta perdida sin escribir")

    setup.docs.batch_update = lost_before_writing
    assert error(lambda: setup.documents.apply_edit(preview["plan_id"])).code == "operation_interrupted"
    setup.docs.style_outside("offer-doc", "Fin", **change)
    result = setup.documents.apply_edit(preview["plan_id"])
    assert result["status"] == "conflict" and result["writes"] is False
    assert result["conflict"]["code"] == "document_changed" and result["conflict"]["write_may_have_occurred"] is True
    assert setup.docs.batches == [] and setup.text() == before
    assert setup.docs.text_style("offer-doc", "Fin") == change


def test_style_plan_written_then_reformatted_by_someone_is_a_conflict_that_keeps_their_format(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = setup.preview([{"op": "set_text_style", "find": "Fin", "occurrences": 1, "highlight_color": "#FFFF00"}])
    setup.docs.lose_answer.add("offer-doc")
    assert error(lambda: setup.documents.apply_edit(preview["plan_id"])).code == "operation_interrupted"
    setup.docs.style_outside("offer-doc", "Fin", background="#0000FF")
    result = setup.documents.apply_edit(preview["plan_id"])
    assert result["status"] == "conflict" and result["conflict"]["write_may_have_occurred"] is True
    assert len(setup.docs.batches) == 1 and setup.docs.text_style("offer-doc", "Fin") == {"background": "#0000FF"}


def test_style_plan_with_a_list_whose_answer_was_lost_is_a_conflict_because_lists_are_not_read_back(
        tmp_path: Path):
    setup = Setup(tmp_path)
    preview = setup.preview([{"op": "set_list", "anchor": "Fin", "list": "bullets"}])
    setup.docs.lose_answer.add("offer-doc")
    assert error(lambda: setup.documents.apply_edit(preview["plan_id"])).code == "operation_interrupted"
    result = setup.documents.apply_edit(preview["plan_id"])
    assert result["status"] == "conflict" and result["conflict"]["write_may_have_occurred"] is True
    assert len(setup.docs.batches) == 1


def test_style_plan_stored_without_checks_is_resent_only_on_its_preview_revision(tmp_path: Path):
    """A plan stored before style checks existed: no read-back, and never a resend on a newer revision."""
    setup = Setup(tmp_path)
    for lose in (False, True):
        preview = setup.preview([{"op": "set_text_style", "find": "Fin", "occurrences": 1, "bold": lose}])
        plan = setup.store.load("person-1", preview["plan_id"])
        metadata = {key: value for key, value in plan.actions[0].metadata.items() if key != "checks"}
        plan_id = setup.store.save(replace(plan, actions=(replace(plan.actions[0], metadata=metadata),)))
        assert "checks" not in setup.store.load("person-1", plan_id).actions[0].metadata
        original = setup.docs.batch_update

        def interrupted(*args, lose=lose):
            setup.docs.batch_update = original
            if lose:
                original(*args)
            raise RuntimeError("respuesta perdida")

        setup.docs.batch_update = interrupted
        assert error(lambda: setup.documents.apply_edit(plan_id)).code == "operation_interrupted"
        result = setup.documents.apply_edit(plan_id)
        if lose:
            assert result["status"] == "conflict" and result["conflict"]["code"] == "document_changed"
        else:
            assert result["status"] == "succeeded"
    assert [batch[2] for batch in setup.docs.batches] == ["rev-1", "rev-2"]


def test_style_plan_whose_answer_was_lost_and_whose_text_then_changed_is_a_conflict(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = setup.preview([{"op": "set_text_style", "find": "Fin", "occurrences": 1, "bold": True}])
    setup.docs.lose_answer.add("offer-doc")
    assert error(lambda: setup.documents.apply_edit(preview["plan_id"])).code == "operation_interrupted"
    setup.docs.edit_outside("offer-doc", 1, "Nuevo ")
    result = setup.documents.apply_edit(preview["plan_id"])
    assert result["status"] == "conflict" and result["conflict"]["code"] == "document_changed"
    assert len(setup.docs.batches) == 1


# -- highlighting and links ------------------------------------------------------------------------

def test_highlight_is_set_changed_and_cleared_on_exactly_the_matches_without_touching_other_styles(tmp_path: Path):
    setup = Setup(tmp_path)
    before = setup.text()
    setup.docs.style_outside("offer-doc", "Plazo: 12", bold=True)
    first = setup.preview([{"op": "set_text_style", "find": "Plazo", "occurrences": 2, "highlight_color": "#ffff00"}])
    assert first["operations"][0]["highlight_color"] == "#FFFF00"
    assert [match["before"] for match in first["operations"][0]["matches"]] == [{"highlight_color": None}] * 2
    setup.documents.apply_edit(first["plan_id"])
    request = setup.docs.batches[0][1][0]["updateTextStyle"]
    assert request["fields"] == "backgroundColor"
    assert request["textStyle"] == {"backgroundColor": {"color": {"rgbColor": {"red": 1.0, "green": 1.0,
                                                                                 "blue": 0.0}}}}
    assert setup.docs.text_style("offer-doc", "Plazo", 0) == {"bold": True, "background": "#FFFF00"}
    assert setup.docs.text_style("offer-doc", "Plazo", 1) == {"background": "#FFFF00"}
    assert setup.docs.text_style("offer-doc", ": 12") == {"bold": True}
    assert setup.docs.text_style("offer-doc", " ampliable") == {}
    second = setup.preview([{"op": "set_text_style", "find": "Plazo", "occurrences": 2, "highlight_color": "#1A2B3C"}])
    assert second["operations"][0]["matches"][0]["before"] == {"highlight_color": "#FFFF00"}
    setup.documents.apply_edit(second["plan_id"])
    assert setup.docs.text_style("offer-doc", "Plazo", 1) == {"background": "#1A2B3C"}
    third = setup.preview([{"op": "set_text_style", "find": "Plazo", "occurrences": 2, "highlight_color": None}])
    setup.documents.apply_edit(third["plan_id"])
    cleared = setup.docs.batches[2][1][0]["updateTextStyle"]
    assert cleared["textStyle"] == {"backgroundColor": {}} and cleared["fields"] == "backgroundColor"
    assert setup.docs.text_style("offer-doc", "Plazo", 0) == {"bold": True}
    assert setup.docs.text_style("offer-doc", "Plazo", 1) == {}
    assert setup.text() == before


def test_link_is_added_changed_and_removed_with_the_complete_url_and_the_formatting_notice(tmp_path: Path):
    setup = Setup(tmp_path)
    before = setup.text()
    url = "https://example.org/especificaciones?lote=1&v=2#anexo"
    first = setup.preview([{"op": "set_text_style", "find": "Memoria técnica", "occurrences": 1, "link_url": url}])
    operation = first["operations"][0]
    assert operation["link_url"] == url and "formato habitual" in operation["notice"]
    assert operation["matches"][0]["before"] == {"link_url": None}
    setup.documents.apply_edit(first["plan_id"])
    request = setup.docs.batches[0][1][0]["updateTextStyle"]
    assert request["textStyle"] == {"link": {"url": url}} and request["fields"] == "link"
    assert setup.docs.text_style("offer-doc", "Memoria técnica") == {"link": url}
    second = setup.preview([{"op": "set_text_style", "find": "Memoria técnica", "occurrences": 1,
                             "link_url": "http://drive.example/d/1"}])
    assert second["operations"][0]["matches"][0]["before"] == {"link_url": url}
    setup.documents.apply_edit(second["plan_id"])
    assert setup.docs.text_style("offer-doc", "Memoria técnica") == {"link": "http://drive.example/d/1"}
    third = setup.preview([{"op": "set_text_style", "find": "Memoria técnica", "occurrences": 1, "link_url": None}])
    assert third["operations"][0]["link_url"] is None and "notice" in third["operations"][0]
    setup.documents.apply_edit(third["plan_id"])
    removed = setup.docs.batches[2][1][0]["updateTextStyle"]
    assert removed["textStyle"] == {} and removed["fields"] == "link"
    assert setup.docs.text_style("offer-doc", "Memoria técnica") == {}
    assert setup.text() == before


def test_flags_highlight_and_link_go_together_in_one_request_with_an_exact_mask(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = setup.preview([{"op": "set_text_style", "find": "Fin", "occurrences": 1, "italic": True,
                              "link_url": "https://example.org/", "highlight_color": "#00ff00"}])
    request = setup.store.load("person-1", preview["plan_id"]).actions[0].metadata["requests"][0]["updateTextStyle"]
    assert request["fields"] == "italic,backgroundColor,link"
    setup.documents.apply_edit(preview["plan_id"])
    assert setup.docs.text_style("offer-doc", "Fin") == {"italic": True, "background": "#00FF00",
                                                         "link": "https://example.org/"}


def test_mixed_before_values_are_reported_as_mixed(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.docs.style_outside("offer-doc", "Pla", 1, background="#FFFF00")
    preview = setup.preview([{"op": "set_text_style", "find": "Plazo", "occurrences": 2, "highlight_color": None}])
    assert [match["before"] for match in preview["operations"][0]["matches"]] == [
        {"highlight_color": None}, {"highlight_color": "mixed"}]


@pytest.mark.parametrize("find, code", [
    ("Plazo:", "partial_link_overlap"),  # the link continues after the span
    ("12 meses", "partial_link_overlap"),  # the link starts before the span
    ("Plazo: 12 meses", None),  # the whole link, split into runs with different flags
    ("Plazo: 12 meses. Plazo", None),  # the span contains the whole link
])
@pytest.mark.parametrize("url", ["https://example.org/nuevo", None])
def test_a_link_change_must_cover_the_whole_existing_link(tmp_path: Path, find, code, url):
    setup = Setup(tmp_path)
    setup.docs.style_outside("offer-doc", "Plazo: 12 meses", link="https://example.org/plazo")
    setup.docs.style_outside("offer-doc", "12", bold=True)
    operation = {"op": "set_text_style", "find": find, "occurrences": 1, "link_url": url}
    if code:
        raised = error(lambda: setup.preview([operation]))
        assert raised.code == code and raised.details["operation"] == 0 and raised.details["text"] == find
        assert setup.plans() == []
    else:
        setup.documents.apply_edit(setup.preview([operation])["plan_id"])
        assert setup.docs.text_style("offer-doc", "Plazo:") == ({"link": url} if url else {})


def test_highlight_does_not_need_the_whole_link_and_adjacent_links_are_not_one_link(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.docs.style_outside("offer-doc", "Plazo: 12 meses", link="https://example.org/plazo")
    setup.docs.style_outside("offer-doc", "Plazo ampliable", link="https://example.org/otro")
    assert setup.preview([{"op": "set_text_style", "find": "12", "occurrences": 1, "highlight_color": "#FFFF00"}])
    # ". " has no link between the two links: each one is whole.
    assert setup.preview([{"op": "set_text_style", "find": "Plazo ampliable", "occurrences": 1,
                           "link_url": None}])
    setup.docs.add("offer-doc", ["ab|cd"])
    setup.docs.style_outside("offer-doc", "ab", link="https://example.org/a")
    setup.docs.style_outside("offer-doc", "cd", link="https://example.org/b")
    setup.docs.style_outside("offer-doc", "|", link="https://example.org/b")
    assert setup.preview([{"op": "set_text_style", "find": "ab", "occurrences": 1, "link_url": None}])
    assert error(lambda: setup.preview([{"op": "set_text_style", "find": "|c", "occurrences": 1, "link_url": None}])
                 ).code == "partial_link_overlap"


def test_a_link_is_not_cut_at_a_hidden_suggested_insertion(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.docs.add("offer-doc", [["AB", ("C", "insert"), "D fin"]])
    setup.docs.style_outside("offer-doc", "ABD", link="https://example.org/")
    raised = error(lambda: setup.preview([{"op": "set_text_style", "find": "AB", "occurrences": 1,
                                           "link_url": None}]))
    assert raised.code in ("partial_link_overlap", "pending_suggestions")
    document = DocumentText.parse(setup.docs.get("offer-doc")["tabs"][0]["documentTab"]["body"])
    assert document.link_crosses(2) and document.gaps[2] == "suggestion"


@pytest.mark.parametrize("suggested, operation, refused", [
    ("backgroundColor", {"highlight_color": "#FFFF00"}, True),
    ("link", {"link_url": None}, True),
    ("bold", {"bold": True}, True),
    ("bold", {"highlight_color": "#FFFF00"}, False),
    ("link", {"highlight_color": None}, False),
])
def test_pending_suggested_style_changes_of_a_requested_property_are_refused(tmp_path: Path, suggested, operation,
                                                                             refused):
    setup = Setup(tmp_path)
    setup.docs.style_outside("offer-doc", "Fin", suggested=suggested)
    call = lambda: setup.preview([{"op": "set_text_style", "find": "Fin", "occurrences": 1, **operation}])
    if refused:
        assert error(call).code == "pending_suggestions" and setup.plans() == []
    else:
        assert call()["operations"]


@pytest.mark.parametrize("field, value", [
    ("highlight_color", "yellow"), ("highlight_color", "#FFF"), ("highlight_color", "FFFF00"),
    ("highlight_color", "#FFFF0G"), ("highlight_color", "#FFFF000"), ("highlight_color", 16776960),
    ("highlight_color", True), ("highlight_color", ""),
    ("link_url", ""), ("link_url", "example.org"), ("link_url", "/relative"), ("link_url", "ftp://example.org"),
    ("link_url", "javascript:alert(1)"), ("link_url", "mailto:a@example.org"), ("link_url", "https://"),
    ("link_url", "https://user:pw@example.org/"), ("link_url", "https://example.org/a b"),
    ("link_url", "https://example.org/\nx"), ("link_url", "https://example.org/\x7f"),
    ("link_url", "https:\\\\example.org"), ("link_url", "https://example.org:99999/"),
    ("link_url", "https://example.org/" + "a" * 2_030), ("link_url", 3), ("link_url", False),
    ("link_url", {"url": "https://example.org"}),
])
def test_invalid_highlight_colors_and_urls_store_no_plan(tmp_path: Path, field, value):
    setup = Setup(tmp_path)
    raised = error(lambda: setup.preview([{"op": "set_text_style", "find": "Fin", "occurrences": 1, field: value}]))
    assert raised.code == "invalid_request" and raised.details == {"operation": 0, "field": field}
    assert setup.plans() == [] and setup.docs.batches == []


def test_valid_urls_are_kept_as_given_and_may_be_long_or_point_to_drive(tmp_path: Path):
    setup = Setup(tmp_path)
    for url in ("HTTPS://Example.org/Path", "https://docs.google.com/document/d/abc/edit",
                "https://example.org/" + "a" * (2_048 - 20), "http://[::1]:8080/x", "https://ejemplo.es/año"):
        preview = setup.preview([{"op": "set_text_style", "find": "Fin", "occurrences": 1, "link_url": url}])
        assert preview["operations"][0]["link_url"] == url


def test_text_model_reads_highlights_links_suggested_styles_and_named_styles():
    body = {"content": [{"endIndex": 1, "sectionBreak": {}}, {"startIndex": 1, "endIndex": 9, "paragraph": {
        "paragraphStyle": {"namedStyleType": "HEADING_2"},
        "elements": [
            {"startIndex": 1, "endIndex": 3, "textRun": {"content": "😀", "textStyle": {
                "bold": True, "backgroundColor": {"color": {"rgbColor": {"red": 1, "blue": 0.2}}}}}},
            {"startIndex": 3, "endIndex": 4, "textRun": {"content": "a", "textStyle": {
                "backgroundColor": {"color": {"rgbColor": {}}}, "link": {"bookmarkId": "id.1"}}}},
            {"startIndex": 4, "endIndex": 5, "textRun": {"content": "b", "textStyle": {"backgroundColor": {}}}},
            {"startIndex": 5, "endIndex": 6, "textRun": {"content": "c", "textStyle": {"link": {"url": "https://x.es"}},
                                                          "suggestedTextStyleChanges": {"s.1": {
                                                              "textStyleSuggestionState": {"linkSuggested": True,
                                                                                           "boldSuggested": False}}}}},
            {"startIndex": 6, "endIndex": 9, "textRun": {"content": "de\n"}}]}}]}
    document = DocumentText.parse(body)
    assert document.text == "😀abcde\n" and document.named_styles == ["HEADING_2"]
    assert document.styles[0] == {"bold": True, "italic": False, "underline": False, "highlight_color": "#FF0033",
                                  "link_url": None}
    assert document.styles[1]["highlight_color"] == "#000000"
    assert document.styles[1]["link_url"] == '{"bookmarkId": "id.1"}'
    assert document.styles[2]["highlight_color"] is None and document.styles[4]["highlight_color"] is None
    assert document.styles[3]["link_url"] == "https://x.es" and document.suggested[3] == {"link"}
    assert document.suggested[2] == frozenset() and not document.link_crosses(2)


# -- document creation -----------------------------------------------------------------------------

def create(setup: Setup, name: str = "Notas", parent: str = "sub", **source) -> dict:
    return setup.documents.preview_creation("root", parent, name, **(source or {"text": "Notas\nsegunda línea 😀"}))


def test_creation_from_text_creates_a_marked_google_doc_containing_the_text(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = create(setup)
    assert preview["kind"] == "document_creation" and preview["parent_folder_id"] == "sub"
    assert preview["name"] == "Notas" and preview["source"] is None and preview["characters"] == 21
    assert setup.drive.created == [] and setup.docs.batches == [] and len(setup.plans()) == 1
    result = setup.documents.apply_creation(preview["plan_id"])
    assert result["status"] == "succeeded" and result["writes"] is True
    created = setup.drive.resources[result["document_id"]]
    assert setup.drive.created == [created.id] and result["web_view_link"] == created.web_view_link
    assert created.name == "Notas" and created.mime_type == GOOGLE_DOC_MIME and created.parents == ("sub",)
    assert created.app_properties["litman_operation_id"] == preview["operation_id"]
    assert setup.docs.plain_text(created.id) == "Notas\nsegunda línea 😀\n"
    (document_id, requests, revision), = setup.docs.batches
    assert document_id == created.id and revision == "rev-1"
    assert requests == [{"insertText": {"location": {"index": 1}, "text": "Notas\nsegunda línea 😀"}}]
    assert setup.documents.read("root", created.id)["text"] == "Notas\nsegunda línea 😀\n"
    replay = setup.documents.apply_creation(preview["plan_id"])
    assert replay["replayed"] is True and replay["writes"] is False and len(setup.drive.created) == 1


def test_creation_converts_a_docx_of_the_dossier_into_a_google_doc(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = create(setup, "Memoria editable", "root", source_file_id="memoria-docx")
    assert preview["source"] == {"file_id": "memoria-docx", "name": "memoria.docx"} and preview["characters"] is None
    result = setup.documents.apply_creation(preview["plan_id"])
    created = setup.drive.resources[result["document_id"]]
    assert created.mime_type == GOOGLE_DOC_MIME and created.parents == ("root",)
    assert created.name == "Memoria editable" and setup.drive.contents[created.id] == DOCX
    assert created.app_properties["litman_operation_id"] == preview["operation_id"]
    assert setup.docs.batches == [] and setup.drive.resources["memoria-docx"].parents == ("sub",)


MARKDOWN = "# Título\n\nUn párrafo con **negrita** y 😀.\n\n- uno\n- dos\n"


def test_creation_from_markdown_uploads_it_converted_to_a_marked_google_doc(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = create(setup, markdown=MARKDOWN)
    assert preview["kind"] == "document_creation" and preview["characters"] == len(MARKDOWN)
    assert preview["source"] is None and setup.drive.created == [] and len(setup.plans()) == 1
    result = setup.documents.apply_creation(preview["plan_id"])
    assert result["status"] == "succeeded" and result["writes"] is True
    created = setup.drive.resources[result["document_id"]]
    assert created.name == "Notas" and created.mime_type == GOOGLE_DOC_MIME and created.parents == ("sub",)
    assert created.app_properties["litman_operation_id"] == preview["operation_id"]
    assert setup.drive.converted == [("Notas", "text/markdown", MARKDOWN.encode("utf-8"))]
    assert setup.docs.batches == [] and result["web_view_link"] == created.web_view_link
    replay = setup.documents.apply_creation(preview["plan_id"])
    assert replay["replayed"] is True and len(setup.drive.created) == 1 and len(setup.drive.converted) == 1


def test_interrupted_markdown_creation_leaves_one_document(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = create(setup, markdown=MARKDOWN)
    setup.drive.crash_on_create = {1}
    assert error(lambda: setup.documents.apply_creation(preview["plan_id"])).code == "operation_interrupted"
    result = setup.documents.apply_creation(preview["plan_id"])
    assert result["status"] == "succeeded" and setup.drive.created == [result["document_id"]]


@pytest.mark.parametrize("markdown", ["", "x" * 100_001, "a\x00b"])
def test_creation_rejects_invalid_markdown(tmp_path: Path, markdown):
    setup = Setup(tmp_path)
    assert error(lambda: create(setup, markdown=markdown)).code == "invalid_request" and setup.plans() == []
    assert create(setup, name="Largo", markdown="x" * 100_000)


@pytest.mark.parametrize("source", [{}, {"text": "x", "source_file_id": "memoria-docx"},
                                    {"text": "x", "markdown": "# x"},
                                    {"markdown": "# x", "source_file_id": "memoria-docx"}])
def test_creation_takes_exactly_one_of_text_markdown_or_source(tmp_path: Path, source):
    setup = Setup(tmp_path)
    call = lambda: setup.documents.preview_creation("root", "sub", "Notas", **source)  # noqa: E731
    assert error(call).code == "invalid_request" and setup.plans() == []


@pytest.mark.parametrize("name, text", [("", "x"), ("  ", "x"), ("a\nb", "x"), ("Notas", ""),
                                        ("Notas", "x\x00"), ("Notas", "x" * (PAGE_SIZE + 1))])
def test_creation_rejects_invalid_names_and_text(tmp_path: Path, name, text):
    setup = Setup(tmp_path)
    assert error(lambda: create(setup, name, text=text)).code == "invalid_request" and setup.plans() == []


@pytest.mark.parametrize("parent", ["offer-doc", "elsewhere", "litman", "litman-sub", "other-root"])
def test_creation_parent_must_be_a_dossier_folder_outside_litman(tmp_path: Path, parent):
    setup = Setup(tmp_path)
    setup.drive.forbidden.discard("other-root")
    assert error(lambda: create(setup, parent=parent)).code == "invalid_parent" and setup.plans() == []


@pytest.mark.parametrize("source, code", [("source", "unsupported_document"), ("sub-doc", "unsupported_document"),
                                          ("loose-docx", "document_outside_tree"),
                                          ("litman-docx", "document_outside_tree")])
def test_creation_source_must_be_a_docx_of_the_dossier(tmp_path: Path, source, code):
    setup = Setup(tmp_path)
    assert error(lambda: create(setup, source_file_id=source)).code == code
    assert setup.plans() == [] and setup.drive.created == []


def test_name_already_used_in_the_parent_is_refused_at_preview_and_at_apply(tmp_path: Path):
    setup = Setup(tmp_path)
    taken = error(lambda: create(setup, "Memoria"))
    assert taken.code == "name_exists" and taken.details["file_ids"] == ["sub-doc"] and setup.plans() == []
    preview = create(setup)
    setup.drive.add(Resource("rival", "Notas", GOOGLE_DOC_MIME, "1", drive_id="shared", parents=("sub",)))
    result = setup.documents.apply_creation(preview["plan_id"])
    assert result["status"] == "conflict" and result["conflict"]["code"] == "name_exists"
    assert result["writes"] is False and setup.drive.created == []


def test_interruption_right_after_creation_leaves_one_document_with_the_text_once(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = create(setup)
    setup.drive.crash_on_create = {1}
    assert error(lambda: setup.documents.apply_creation(preview["plan_id"])).code == "operation_interrupted"
    result = setup.documents.apply_creation(preview["plan_id"])
    assert result["status"] == "succeeded" and setup.drive.created == [result["document_id"]]
    assert setup.docs.plain_text(result["document_id"]) == "Notas\nsegunda línea 😀\n"
    assert len(setup.docs.batches) == 1


def test_lost_answer_of_the_initial_text_is_completed_without_writing_it_twice(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = create(setup)
    setup.docs.lose_answer = {"new-1"}
    assert error(lambda: setup.documents.apply_creation(preview["plan_id"])).code == "operation_interrupted"
    result = setup.documents.apply_creation(preview["plan_id"])
    assert result["status"] == "succeeded" and result["document_id"] == "new-1"
    assert setup.docs.plain_text("new-1") == "Notas\nsegunda línea 😀\n" and len(setup.docs.batches) == 1


def test_new_document_edited_before_the_initial_text_is_a_conflict(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = create(setup)
    setup.drive.crash_on_create = {1}
    error(lambda: setup.documents.apply_creation(preview["plan_id"]))
    setup.docs.edit_outside("new-1", 1, "Escrito a mano")
    result = setup.documents.apply_creation(preview["plan_id"])
    assert result["status"] == "conflict" and result["conflict"]["code"] == "document_changed"
    assert setup.docs.batches == [] and setup.docs.plain_text("new-1") == "Escrito a mano\n"


def test_source_changed_after_preview_is_a_conflict_without_creating(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = create(setup, source_file_id="memoria-docx")
    setup.drive.write_text("memoria-docx", "otro contenido")
    result = setup.documents.apply_creation(preview["plan_id"])
    assert result["status"] == "conflict" and result["conflict"]["code"] == "source_changed"
    assert setup.drive.created == []


def test_creation_rechecks_the_parent_at_apply(tmp_path: Path):
    setup = Setup(tmp_path)
    preview = create(setup)
    setup.drive.resources["sub"] = replace(setup.drive.resources["sub"], parents=("elsewhere",))
    assert error(lambda: setup.documents.apply_creation(preview["plan_id"])).code == "invalid_parent"
    assert setup.drive.created == []


def test_creation_with_the_read_only_adapter_stops_at_the_concurrency_gate(tmp_path: Path):
    setup = Setup(tmp_path, shared_state=False)
    result = setup.documents.apply_creation(create(setup)["plan_id"])
    assert result["status"] == "pending_concurrency_gate" and result["writes"] is False
    assert setup.drive.created == [] and setup.docs.batches == []
