from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fakes import AtomicSharedState, FakeDocs, dossier_drive

from litman_harness.dossier.comments import CommentService
from litman_harness.dossier.documents import DocumentService
from litman_harness.dossier.models import FOLDER_MIME, GOOGLE_DOC_MIME, Resource
from litman_harness.dossier.service import ExpedienteService, action_id
from litman_harness.errors import HarnessError
from litman_harness.plans import PlanStore
from litman_harness.plans.models import OperationRecord, OperationStatus, Plan, PlanAction

PDF = "application/pdf"
TEXT = ["Memoria técnica", "El plazo de ejecución es de 12 meses.", "Equipo 😀 con café", "Plazo repetido",
        "Plazo repetido"]


class Setup:
    """A connected dossier with a PDF (``doc``, one historical Drive comment ``c1``) and a single-tab Google Doc
    (``gdoc``) holding a historical Drive comment ``d1`` and a native thread ``n1`` anchored to "12 meses"."""

    def __init__(self, tmp_path: Path):
        self.drive = dossier_drive()
        self.drive.add(Resource("doc", "memoria.pdf", PDF, "1", 10, "shared", parents=("root",),
                                capabilities={"canComment": True}), b"contenido")
        self.drive.add(Resource("no-comment", "sin_permiso.pdf", PDF, "1", 1, "shared", parents=("root",),
                                capabilities={"canComment": False}))
        editor = {"canComment": True, "canEdit": True}
        self.drive.add(Resource("gdoc", "Memoria", GOOGLE_DOC_MIME, "1", drive_id="shared", parents=("root",),
                                capabilities=editor))
        self.drive.add(Resource("tabs", "Pestañas", GOOGLE_DOC_MIME, "1", drive_id="shared", parents=("root",),
                                capabilities=editor))
        self.drive.add(Resource("litman", "_LitMan", FOLDER_MIME, "1", drive_id="shared", parents=("root",)))
        self.drive.add(Resource("internal", "Interno", GOOGLE_DOC_MIME, "1", drive_id="shared",
                                parents=("litman",), capabilities=editor))
        self.drive.comment_threads["doc"] = [
            {"id": "c1", "content": "Revisar el plazo", "author": {"displayName": "Ana", "me": False},
             "createdTime": "2026-01-01T00:00:00Z", "resolved": False, "replies": []}]
        self.drive.comment_threads["gdoc"] = [
            {"id": "d1", "content": "Comentario general antiguo", "author": {"displayName": "Ana", "me": False},
             "createdTime": "2026-01-01T00:00:00Z", "resolved": False, "replies": []}]
        self.docs = FakeDocs()
        self.docs.add("gdoc", TEXT)
        self.docs.add("tabs", ["Texto"], tabs=2)
        self.docs.add("internal", ["Texto"])
        self.docs.add_thread("gdoc", "n1", "¿Seguro?", snippet="12 meses")
        self.store = PlanStore(tmp_path / "plans")
        self.plans = tmp_path / "plans"
        self.state = AtomicSharedState(self.drive)
        self.dossier = ExpedienteService(self.drive, self.store, self.state)
        self.service = CommentService(self.dossier, DocumentService(self.dossier, self.docs))

        def no_general_comments(*args):
            raise AssertionError("nunca se crea un comentario general de Drive")
        self.drive.create_comment = no_general_comments

    def preview(self, file_id: str, operations: list[dict]) -> dict:
        return self.service.preview("root", file_id, operations)

    def apply(self, plan_id: str) -> dict:
        return self.service.apply(plan_id)

    def native(self, comment_id: str) -> dict:
        return next(t for t in self.docs.threads["gdoc"] if t["commentId"] == comment_id)

    def saved_plans(self) -> int:
        return len(list(self.plans.rglob("*.json"))) if self.plans.exists() else 0


def error(call) -> HarnessError:
    with pytest.raises(HarnessError) as raised:
        call()
    return raised.value


ADD = {"op": "add", "content": "Confirmar con el cliente", "anchor": "12 meses"}


# -- AC-01: anchored preview ---------------------------------------------------------------------

def test_an_anchored_add_previews_content_quote_tab_range_and_context(tmp_path: Path):
    setup = Setup(tmp_path)
    result = setup.preview("gdoc", [ADD])
    (action,) = result["actions"]
    assert result["kind"] == "comment_changes" and action["kind"] == "docs_comment_batch"
    assert action["expected_version"] == "rev-1" and action["metadata"]["backend"] == "docs"
    (preview,) = result["operations"]
    text = setup.docs.plain_text("gdoc")
    start = 1 + text.index("12 meses")
    assert preview == {"op": "add", "content": "Confirmar con el cliente", "quoted_text": "12 meses",
                       "tab_id": "t.0", "range": {"start_index": start, "end_index": start + 8},
                       "context": {"offset": text.index("12 meses"), "text": "12 meses",
                                   "before": text[:text.index("12 meses")],
                                   "after": text[text.index("12 meses") + 8:][:80]}}
    assert action["metadata"]["requests"] == [{"insertComment": {
        "range": {"startIndex": start, "endIndex": start + 8, "tabId": "t.0"},
        "content": "Confirmar con el cliente"}}]


def test_a_section_title_and_an_accented_emoji_phrase_are_anchored_in_utf16_units(tmp_path: Path):
    setup = Setup(tmp_path)
    result = setup.preview("gdoc", [{"op": "add", "content": "Título", "anchor": "Memoria técnica"},
                                    {"op": "add", "content": "Revisar", "anchor": "😀 con café"}])
    first, second = (request["insertComment"]["range"] for request in result["actions"][0]["metadata"]["requests"])
    assert first == {"startIndex": 1, "endIndex": 16, "tabId": "t.0"}
    text = setup.docs.plain_text("gdoc")
    start = 1 + len(text[:text.index("😀")].encode("utf-16-le")) // 2
    assert second == {"startIndex": start, "endIndex": start + 2 + len(" con café"), "tabId": "t.0"}


@pytest.mark.parametrize("operations, code", [
    ([{"op": "add", "content": "x"}], "invalid_request"),  # no anchor
    ([{"op": "add", "content": "x", "anchor": ""}], "invalid_request"),
    ([{"op": "add", "content": "x", "anchor": "a" * 1001}], "invalid_request"),
    ([{"op": "add", "content": "x", "anchor": "12 meses.\nEquipo"}], "invalid_request"),  # two paragraphs
    ([{"op": "add", "content": "x", "anchor": "No aparece"}], "anchor_not_unique"),
    ([{"op": "add", "content": "x", "anchor": "Plazo repetido"}], "anchor_not_unique"),
    ([{"op": "add", "content": "é" * 1025, "anchor": "12 meses"}], "invalid_request"),  # 2050 UTF-8 bytes
    ([{"op": "add", "content": "x", "anchor": "12 meses", "comment_id": "c"}], "invalid_request"),
    ([ADD, {"op": "reply", "comment_id": "d1", "content": "x"}], "mixed_comment_backends"),
    ([{"op": "reply", "comment_id": "docs:ghost", "content": "x"}], "comment_not_found"),
])
def test_invalid_anchored_requests_fail_before_saving_a_plan(tmp_path: Path, operations, code):
    setup = Setup(tmp_path)
    assert error(lambda: setup.preview("gdoc", operations)).code == code
    assert setup.saved_plans() == 0 and setup.docs.comment_batches == []


def test_native_content_is_limited_in_utf8_bytes_not_characters(tmp_path: Path):
    setup = Setup(tmp_path)
    assert setup.preview("gdoc", [{"op": "add", "content": "é" * 1024, "anchor": "12 meses"}])
    assert error(lambda: setup.preview("gdoc", [{"op": "add", "content": "😀" * 513, "anchor": "12 meses"}])
                 ).code == "invalid_request"


@pytest.mark.parametrize("file_id, code", [("doc", "unsupported_document"), ("tabs", "unsupported_document"),
                                           ("internal", "document_outside_tree"),
                                           ("other-file", "document_outside_tree")])
def test_adds_outside_a_single_tab_google_doc_of_the_tree_are_refused(tmp_path: Path, file_id, code):
    setup = Setup(tmp_path)
    setup.drive.forbidden.discard("other-file")
    setup.drive.forbidden.discard("other-root")
    assert error(lambda: setup.preview(file_id, [{"op": "add", "content": "x", "anchor": "Texto"}])).code == code
    assert setup.saved_plans() == 0


def test_an_anchor_touching_a_pending_suggestion_is_refused(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.docs.add("gdoc", [["Plazo ", ("nuevo ", "insert"), "de obra"]])
    assert error(lambda: setup.preview("gdoc", [{"op": "add", "content": "x", "anchor": "Plazo "}])
                 ).code == "pending_suggestions"


def test_a_commenter_only_account_cannot_create_anchored_comments(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.drive.resources["gdoc"] = replace(setup.drive.resources["gdoc"], capabilities={"canComment": True})
    failure = error(lambda: setup.preview("gdoc", [ADD]))
    assert failure.code == "insufficient_capability" and "edición" in str(failure)
    # Historical Drive threads stay available with comment access only.
    assert setup.preview("gdoc", [{"op": "reply", "comment_id": "d1", "content": "Visto"}])


# -- AC-02: native apply -------------------------------------------------------------------------

def test_apply_inserts_an_anchored_native_comment_and_returns_its_routable_id(tmp_path: Path):
    setup = Setup(tmp_path)
    before = setup.docs.plain_text("gdoc")
    plan = setup.preview("gdoc", [ADD])
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded"
    ((document_id, requests, revision),) = setup.docs.comment_batches
    assert document_id == "gdoc" and revision == "rev-1" and list(requests[0]) == ["insertComment"]
    (output,) = result["results"]
    raw_id = output["comment_id"].removeprefix("docs:")
    assert output["comment_id"].startswith("docs:") and setup.native(raw_id)["plainTextQuote"] == "12 meses"
    assert setup.docs.plain_text("gdoc") == before and setup.docs.batches == []
    assert setup.apply(plan["plan_id"])["replayed"] is True and len(setup.docs.comment_batches) == 1


def test_a_document_changed_after_the_preview_is_a_conflict_without_retargeting(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("gdoc", [ADD])
    setup.docs.edit_outside("gdoc", 1, "Nuevo ")
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "conflict" and result["conflict"]["code"] == "document_changed"
    assert setup.docs.comment_batches == []


def test_a_stale_revision_refused_by_google_is_a_conflict(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("gdoc", [ADD])
    send = setup.docs.batch_update_comments

    def edited_meanwhile(document_id, requests, revision):
        setup.docs.edit_outside(document_id, 1, "Nuevo ")
        return send(document_id, requests, revision)
    setup.docs.batch_update_comments = edited_meanwhile
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "conflict" and result["conflict"]["code"] == "document_changed"
    assert len(setup.docs.threads["gdoc"]) == 1


@pytest.mark.parametrize("change, code", [({"capabilities": {"canComment": True}}, "insufficient_capability"),
                                          ({"parents": ("elsewhere",)}, "document_outside_tree")])
def test_capabilities_and_membership_are_rechecked_on_apply(tmp_path: Path, change, code):
    setup = Setup(tmp_path)
    plan = setup.preview("gdoc", [ADD])
    setup.drive.resources["gdoc"] = replace(setup.drive.resources["gdoc"], **change)
    assert error(lambda: setup.apply(plan["plan_id"])).code == code
    assert setup.docs.comment_batches == []


def _legacy_plan(setup: Setup, *actions: PlanAction) -> Plan:
    plan = Plan("comment_changes", "root", setup.dossier.account_id(), actions, {})
    setup.store.save(plan)
    return plan


def test_an_unfinished_legacy_unanchored_add_is_refused_before_any_write(tmp_path: Path):
    setup = Setup(tmp_path)
    replies = len(setup.drive.comment_threads["doc"][0]["replies"])
    plan = _legacy_plan(setup, PlanAction("reply", "doc", "Visto", "0", metadata={
        "index": 0, "created_after": None, "comment_id": "c1"}),
        PlanAction("add", "doc", "General", "1", metadata={"index": 1, "created_after": None, "comment_id": None}))
    failure = error(lambda: setup.apply(plan.id))
    assert failure.code == "comment_anchor_required" and failure.details["operations"] == [1]
    assert "anchor" in str(failure)
    assert len(setup.drive.comment_threads["doc"][0]["replies"]) == replies
    assert error(lambda: setup.apply(plan.id)).code == "comment_anchor_required"


def test_a_legacy_plan_whose_add_already_completed_finishes_its_pending_reply(tmp_path: Path):
    setup = Setup(tmp_path)
    add = PlanAction("add", "doc", "General", "0", metadata={"index": 0, "created_after": None, "comment_id": None})
    reply = PlanAction("reply", "doc", "Visto", "1", metadata={"index": 1, "created_after": None,
                                                                "comment_id": "c1"})
    plan = _legacy_plan(setup, add, reply)
    done = action_id(plan, add)
    setup.store.save_operation(plan.account_id, plan.operation_id, OperationRecord(
        plan.operation_id, plan.id, plan.kind, OperationStatus.RECOVERABLE, (done,), (),
        {done: {"comment_id": "old-general"}}))
    result = setup.apply(plan.id)
    assert result["status"] == "succeeded"
    assert result["results"][0] == {"comment_id": "old-general"}
    assert result["results"][1]["comment_id"] == "c1"


# -- AC-03: verified persistence and recovery ----------------------------------------------------

def test_a_failed_save_is_never_reported_as_created_nor_sent_again(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("gdoc", [ADD])
    setup.docs.comment_fault["gdoc"] = "failed"
    failure = error(lambda: setup.apply(plan["plan_id"]))
    assert failure.code == "comment_save_failed" and failure.details["write_may_have_occurred"] is True
    assert error(lambda: setup.apply(plan["plan_id"])).code == "comment_save_failed"
    assert len(setup.docs.comment_batches) == 1 and len(setup.docs.threads["gdoc"]) == 1


def test_a_failed_save_state_is_completed_only_by_observed_evidence(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("gdoc", [ADD])
    setup.docs.comment_fault["gdoc"] = "saved_but_failed"
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded" and len(setup.docs.comment_batches) == 1


@pytest.mark.parametrize("fault", ["no_state", "no_ids"])
def test_a_missing_save_state_or_missing_ids_are_reconciled_by_read_back(tmp_path: Path, fault):
    setup = Setup(tmp_path)
    plan = setup.preview("gdoc", [ADD])
    setup.docs.comment_fault["gdoc"] = fault
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded"
    assert setup.native(result["results"][0]["comment_id"].removeprefix("docs:"))["headPost"]["content"] == \
        ADD["content"]


def test_a_lost_answer_is_uncertain_then_reconciled_without_a_second_insertion(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("gdoc", [ADD, {**ADD}])
    setup.docs.comment_fault["gdoc"] = "lost"
    failure = error(lambda: setup.apply(plan["plan_id"]))
    assert failure.code == "comment_write_uncertain" and failure.details["write_may_have_occurred"] is True
    assert failure.details["operation_id"] == plan["operation_id"]
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded" and len(setup.docs.comment_batches) == 1
    first, second = (output["comment_id"] for output in result["results"])
    assert first != second and len(setup.docs.threads["gdoc"]) == 3


def test_a_lost_unsaved_batch_stays_uncertain_and_is_never_resent(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("gdoc", [ADD])
    setup.docs.comment_fault["gdoc"] = "lost_unsaved"
    for _ in range(2):
        failure = error(lambda: setup.apply(plan["plan_id"]))
        assert failure.code == "comment_write_uncertain" and failure.details["write_may_have_occurred"] is True
    assert len(setup.docs.comment_batches) == 1


def test_a_failed_read_back_after_saving_keeps_the_evidence_and_reconciles_later(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("gdoc", [ADD])
    setup.docs.failing_comment_reads = 0
    send = setup.docs.batch_update_comments

    def then_reads_fail(*args):
        response = send(*args)
        setup.docs.failing_comment_reads = 1
        return response
    setup.docs.batch_update_comments = then_reads_fail
    assert error(lambda: setup.apply(plan["plan_id"])).code == "comment_write_uncertain"
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded" and len(setup.docs.comment_batches) == 1


def test_two_fresh_candidates_for_one_lost_add_are_a_conflict(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("gdoc", [ADD])
    setup.docs.comment_fault["gdoc"] = "lost"
    error(lambda: setup.apply(plan["plan_id"]))
    setup.docs.add_thread("gdoc", "twin", ADD["content"], snippet="12 meses", me=True,
                          created="2026-10-21T11:00:00Z")
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "conflict" and len(setup.docs.comment_batches) == 1


def test_a_reconciled_comment_without_its_live_anchor_is_a_conflict(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("gdoc", [ADD])
    setup.docs.comment_fault["gdoc"] = "lost"
    error(lambda: setup.apply(plan["plan_id"]))
    created = setup.docs.threads["gdoc"][-1]
    del setup.docs.anchors["gdoc"][created["anchorId"]]
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "conflict" and result["conflict"]["code"] == "comment_anchor_unverified"


def test_a_batch_google_refuses_writes_nothing_and_can_be_retried(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("gdoc", [ADD])
    setup.docs.comment_fault["gdoc"] = "rejected"
    assert error(lambda: setup.apply(plan["plan_id"])).code == "docs_request_rejected"
    assert setup.apply(plan["plan_id"])["status"] == "succeeded" and len(setup.docs.comment_batches) == 2


def test_a_lost_reply_is_reconciled_by_its_parent_thread_and_new_post(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("gdoc", [{"op": "reply", "comment_id": "docs:n1", "content": "De acuerdo"}])
    setup.docs.comment_fault["gdoc"] = "lost"
    assert error(lambda: setup.apply(plan["plan_id"])).code == "comment_write_uncertain"
    result = setup.apply(plan["plan_id"])
    (post,) = setup.native("n1")["replies"]
    assert result["results"] == [{"comment_id": "docs:n1", "reply_id": post["postId"]}]


# -- AC-04: native and historical threads ------------------------------------------------------

def test_native_threads_are_replied_and_resolved_through_docs(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("gdoc", [{"op": "reply", "comment_id": "docs:n1", "content": "De acuerdo"},
                                  {"op": "resolve", "comment_id": "docs:n1", "content": "Hecho"}])
    assert [p["quoted_text"] for p in plan["operations"]] == ["12 meses", "12 meses"]
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded"
    ((_, requests, _),) = setup.docs.comment_batches
    assert requests == [{"addCommentReply": {"commentId": "n1", "post": {"content": "De acuerdo"}}},
                        {"addCommentReply": {"commentId": "n1", "post": {"content": "Hecho",
                                                                         "commentAction": "RESOLVE"}}}]
    assert setup.native("n1")["status"] == "RESOLVED"
    assert [output["comment_id"] for output in result["results"]] == ["docs:n1", "docs:n1"]


def test_resolving_an_already_resolved_native_thread_sends_nothing(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("gdoc", [{"op": "resolve", "comment_id": "docs:n1"}])
    setup.native("n1")["status"] = "RESOLVED"
    result = setup.apply(plan["plan_id"])
    assert result["results"] == [{"comment_id": "docs:n1", "reply_id": None}] and setup.docs.comment_batches == []


def test_historical_drive_threads_on_a_google_doc_keep_routing_through_drive(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("gdoc", [{"op": "reply", "comment_id": "d1", "content": "Visto"},
                                  {"op": "resolve", "comment_id": "d1"}])
    assert [action["metadata"]["backend"] for action in plan["actions"]] == ["drive", "drive"]
    assert setup.apply(plan["plan_id"])["status"] == "succeeded"
    assert setup.drive.comment_threads["gdoc"][0]["resolved"] is True and setup.docs.comment_batches == []


def test_listing_shows_native_and_historical_threads_with_anchor_metadata(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.docs.add_thread("gdoc", "orphan", "Sin ancla")
    setup.docs.add_thread("gdoc", "d-same", "Visto por las dos APIs", status="RESOLVED")
    setup.drive.comment_threads["gdoc"].append({"id": "d-same", "content": "Visto por las dos APIs",
                                                "createdTime": "2026-01-01T00:00:00Z", "resolved": True})
    item = setup.drive.get("gdoc")
    listed = setup.service.listed(item, include_resolved=True)
    assert [(c["id"], c["source"]) for c in listed] == [("docs:n1", "docs"), ("docs:orphan", "docs"),
                                                        ("docs:d-same", "docs"), ("d1", "drive")]
    native = listed[0]
    text = setup.docs.plain_text("gdoc")
    start = 1 + text.index("12 meses")
    assert native["quoted_text"] == "12 meses" and native["anchor"] == {
        "tab_id": "t.0", "ranges": [{"start_index": start, "end_index": start + 8}], "text": "12 meses"}
    assert listed[1]["anchor"] is None and listed[3]["anchor"] is None
    assert [c["id"] for c in setup.service.listed(item, include_resolved=False)] == ["docs:n1", "docs:orphan", "d1"]


def test_a_native_read_failure_is_not_hidden_behind_drive_comments(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.docs.failing_comment_reads = 1
    assert error(lambda: setup.service.listed(setup.drive.get("gdoc"), True)).code == "docs_error"


# -- historical Drive comments on other files ------------------------------------------------------

def test_reply_and_resolve_on_a_pdf_still_go_through_drive(tmp_path: Path):
    setup = Setup(tmp_path)
    result = setup.preview("doc", [{"op": "reply", "comment_id": "c1", "content": "De acuerdo"},
                                   {"op": "resolve", "comment_id": "c1"}])
    assert [action["kind"] for action in result["actions"]] == ["reply", "resolve"]
    assert result["operations"][0]["quoted_text"] == "Revisar el plazo"
    assert setup.apply(result["plan_id"])["status"] == "succeeded"
    comment = setup.drive.comment_threads["doc"][0]
    assert comment["resolved"] is True and [r["action"] for r in comment["replies"]] == [None, "resolve"]


def test_a_file_without_comment_permission_is_insufficient_capability(tmp_path: Path):
    setup = Setup(tmp_path)
    assert error(lambda: setup.preview("no-comment", [{"op": "reply", "comment_id": "c1", "content": "x"}])
                 ).code == "insufficient_capability"


def test_unknown_drive_comment_id_is_comment_not_found(tmp_path: Path):
    setup = Setup(tmp_path)
    assert error(lambda: setup.preview("doc", [{"op": "reply", "comment_id": "ghost", "content": "x"}])
                 ).code == "comment_not_found"


@pytest.mark.parametrize("operations", [
    [{"op": "reply", "comment_id": "c1", "content": ""}],
    [{"op": "reply", "comment_id": "c1", "content": "x" * 4097}],
    [{"op": "reply", "content": "x"}],
    [{"op": "unknown", "content": "x"}],
    [],
])
def test_invalid_operations_are_rejected_before_storing_a_plan(tmp_path: Path, operations: list[dict]):
    setup = Setup(tmp_path)
    assert error(lambda: setup.preview("doc", operations)).code == "invalid_request"
    assert setup.saved_plans() == 0


def test_resolve_completes_without_a_call_when_already_resolved(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("doc", [{"op": "resolve", "comment_id": "c1"}])
    setup.drive.comment_threads["doc"][0]["resolved"] = True
    assert setup.apply(plan["plan_id"])["status"] == "succeeded"
    assert setup.drive.comment_threads["doc"][0]["replies"] == []


def test_a_lost_drive_reply_is_adopted_instead_of_duplicated(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("doc", [{"op": "reply", "comment_id": "c1", "content": "De acuerdo"}])
    setup.drive.comment_threads["doc"][0]["replies"].append(
        {"id": "lost", "content": "De acuerdo", "author": {"me": True}, "createdTime": "2026-06-01T00:00:00Z",
         "deleted": False})
    result = setup.apply(plan["plan_id"])
    assert result["results"] == [{"comment_id": "c1", "reply_id": "lost"}]
    assert len(setup.drive.comment_threads["doc"][0]["replies"]) == 1


def test_more_than_one_drive_resume_candidate_is_a_conflict(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("doc", [{"op": "reply", "comment_id": "c1", "content": "De acuerdo"}])
    for suffix in ("a", "b"):
        setup.drive.comment_threads["doc"][0]["replies"].append(
            {"id": f"lost-{suffix}", "content": "De acuerdo", "author": {"me": True},
             "createdTime": "2026-06-01T00:00:00Z", "deleted": False})
    assert setup.apply(plan["plan_id"])["status"] == "conflict"


def test_two_identical_drive_replies_each_get_created(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("doc", [{"op": "reply", "comment_id": "c1", "content": "+1"},
                                 {"op": "reply", "comment_id": "c1", "content": "+1"}])
    result = setup.apply(plan["plan_id"])
    assert result["results"][0]["reply_id"] != result["results"][1]["reply_id"]


def test_losing_comment_permission_is_rechecked_on_apply(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("doc", [{"op": "reply", "comment_id": "c1", "content": "x"}])
    setup.drive.resources["doc"] = replace(setup.drive.resources["doc"], capabilities={"canComment": False})
    assert error(lambda: setup.apply(plan["plan_id"])).code == "insufficient_capability"
