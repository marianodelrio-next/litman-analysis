from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fakes import AtomicSharedState, dossier_drive

from litman_harness.dossier.comments import CommentService
from litman_harness.dossier.models import Resource
from litman_harness.dossier.service import ExpedienteService
from litman_harness.errors import HarnessError
from litman_harness.plans import PlanStore

PDF = "application/pdf"


class Setup:
    """A connected dossier with one commentable file (``doc``) with an existing comment (``c1``)."""

    def __init__(self, tmp_path: Path):
        self.drive = dossier_drive()
        self.drive.add(Resource("doc", "memoria.pdf", PDF, "1", 10, "shared", parents=("root",),
                                capabilities={"canComment": True}), b"contenido")
        self.drive.add(Resource("no-comment", "sin_permiso.pdf", PDF, "1", 1, "shared", parents=("root",),
                                capabilities={"canComment": False}))
        self.drive.comment_threads["doc"] = [
            {"id": "c1", "content": "Revisar el plazo", "author": {"displayName": "Ana", "me": False},
             "createdTime": "2026-01-01T00:00:00Z", "resolved": False, "replies": []}]
        self.store = PlanStore(tmp_path / "plans")
        self.state = AtomicSharedState(self.drive)
        self.dossier = ExpedienteService(self.drive, self.store, self.state)
        self.service = CommentService(self.dossier)

    def preview(self, file_id: str, operations: list[dict]) -> dict:
        return self.service.preview("root", file_id, operations)

    def apply(self, plan_id: str) -> dict:
        return self.service.apply(plan_id)


# -- preview validation ------------------------------------------------------------------------

def test_add_reply_and_resolve_are_previewed_in_one_plan(tmp_path: Path):
    setup = Setup(tmp_path)
    result = setup.preview("doc", [{"op": "add", "content": "Nuevo comentario"},
                                   {"op": "reply", "comment_id": "c1", "content": "De acuerdo"},
                                   {"op": "resolve", "comment_id": "c1"}])
    assert result["kind"] == "comment_changes" and result["file_id"] == "doc"
    assert [action["kind"] for action in result["actions"]] == ["add", "reply", "resolve"]
    assert result["operations"][1]["quoted_text"] == "Revisar el plazo"


def test_file_outside_the_tree_is_document_outside_tree(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.drive.forbidden.discard("other-file")
    setup.drive.forbidden.discard("other-root")
    with pytest.raises(HarnessError) as raised:
        setup.preview("other-file", [{"op": "add", "content": "x"}])
    assert raised.value.code == "document_outside_tree"


def test_a_file_without_comment_permission_is_insufficient_capability(tmp_path: Path):
    setup = Setup(tmp_path)
    with pytest.raises(HarnessError) as raised:
        setup.preview("no-comment", [{"op": "add", "content": "x"}])
    assert raised.value.code == "insufficient_capability"


def test_unknown_or_deleted_comment_id_is_comment_not_found(tmp_path: Path):
    setup = Setup(tmp_path)
    with pytest.raises(HarnessError) as raised:
        setup.preview("doc", [{"op": "reply", "comment_id": "ghost", "content": "x"}])
    assert raised.value.code == "comment_not_found"


@pytest.mark.parametrize("operations", [
    [{"op": "add"}],  # missing content
    [{"op": "add", "content": ""}],  # empty content
    [{"op": "add", "content": "x" * 4097}],  # too long
    [{"op": "reply", "content": "x"}],  # missing comment_id
    [{"op": "unknown", "content": "x"}],  # bad op
    [],  # empty
])
def test_invalid_operations_are_rejected_before_storing_a_plan(tmp_path: Path, operations: list[dict]):
    setup = Setup(tmp_path)
    with pytest.raises(HarnessError) as raised:
        setup.preview("doc", operations)
    assert raised.value.code == "invalid_request"


def test_resolve_accepts_an_optional_content(tmp_path: Path):
    setup = Setup(tmp_path)
    result = setup.preview("doc", [{"op": "resolve", "comment_id": "c1"},
                                   {"op": "resolve", "comment_id": "c1", "content": "Resuelto"}])
    assert len(result["actions"]) == 2


# -- apply --------------------------------------------------------------------------------------

def test_apply_creates_an_unanchored_comment(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("doc", [{"op": "add", "content": "Nuevo comentario"}])
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded"
    created = next(c for c in setup.drive.comment_threads["doc"] if c["content"] == "Nuevo comentario")
    assert created["author"]["me"] is True


def test_apply_creates_a_reply(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("doc", [{"op": "reply", "comment_id": "c1", "content": "De acuerdo"}])
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded"
    comment = setup.drive.comment_threads["doc"][0]
    reply = next(r for r in comment["replies"] if r["content"] == "De acuerdo")
    assert reply["action"] is None


def test_apply_resolves_with_a_reply_carrying_the_resolve_action(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("doc", [{"op": "resolve", "comment_id": "c1", "content": "Hecho"}])
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded"
    comment = setup.drive.comment_threads["doc"][0]
    assert comment["resolved"] is True
    reply = next(r for r in comment["replies"] if r["action"] == "resolve")
    assert reply["content"] == "Hecho"


def test_resolve_completes_without_a_call_when_already_resolved(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("doc", [{"op": "resolve", "comment_id": "c1"}])
    setup.drive.comment_threads["doc"][0]["resolved"] = True
    before = len(setup.drive.comment_threads["doc"][0]["replies"])
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded"
    assert len(setup.drive.comment_threads["doc"][0]["replies"]) == before


def test_resume_adopts_a_lost_answer_instead_of_duplicating_it(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("doc", [{"op": "add", "content": "Nuevo comentario"}])
    # Simulate a lost answer: the comment was already created by this account after the preview.
    setup.drive.comment_threads["doc"].append(
        {"id": "lost", "content": "Nuevo comentario", "author": {"me": True},
         "createdTime": "2026-06-01T00:00:00Z", "resolved": False, "replies": []})
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded"
    matching = [c for c in setup.drive.comment_threads["doc"] if c["content"] == "Nuevo comentario"]
    assert len(matching) == 1 and matching[0]["id"] == "lost"


def test_resume_does_not_adopt_a_match_created_before_the_preview(tmp_path: Path):
    setup = Setup(tmp_path)
    # A pre-existing comment with the same content, but older than the preview's snapshot: not adopted.
    setup.drive.comment_threads["doc"].append(
        {"id": "old", "content": "Repetido", "author": {"me": True},
         "createdTime": "2025-01-01T00:00:00Z", "resolved": False, "replies": []})
    plan = setup.preview("doc", [{"op": "add", "content": "Repetido"}])
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded"
    matching = [c for c in setup.drive.comment_threads["doc"] if c["content"] == "Repetido"]
    assert len(matching) == 2


def test_more_than_one_resume_candidate_is_a_conflict(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("doc", [{"op": "add", "content": "Nuevo comentario"}])
    for suffix in ("a", "b"):
        setup.drive.comment_threads["doc"].append(
            {"id": f"lost-{suffix}", "content": "Nuevo comentario", "author": {"me": True},
             "createdTime": "2026-06-01T00:00:00Z", "resolved": False, "replies": []})
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "conflict"


def test_resume_matches_reply_and_resolve_candidates_independently(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("doc", [{"op": "reply", "comment_id": "c1", "content": "De acuerdo"},
                                 {"op": "resolve", "comment_id": "c1", "content": "De acuerdo"}])
    # Same content for a plain reply and a resolve reply: a resolve-type reply must not satisfy a plain-reply match.
    setup.drive.comment_threads["doc"][0]["replies"].append(
        {"id": "resolved-reply", "content": "De acuerdo", "author": {"me": True}, "action": "resolve",
         "createdTime": "2026-06-01T00:00:00Z", "deleted": False})
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded"
    replies = setup.drive.comment_threads["doc"][0]["replies"]
    plain = [r for r in replies if not r.get("action")]
    resolve = [r for r in replies if r.get("action") == "resolve"]
    assert len(plain) == 1 and len(resolve) == 1


def test_two_actions_with_identical_content_each_get_their_own_comment(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("doc", [{"op": "add", "content": "Mismo texto"}, {"op": "add", "content": "Mismo texto"}])
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded"
    matching = [c for c in setup.drive.comment_threads["doc"] if c["content"] == "Mismo texto"]
    assert len(matching) == 2
    assert result["results"][0]["comment_id"] != result["results"][1]["comment_id"]


def test_two_replies_to_the_same_comment_with_identical_content_each_get_created(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("doc", [{"op": "reply", "comment_id": "c1", "content": "+1"},
                                 {"op": "reply", "comment_id": "c1", "content": "+1"}])
    result = setup.apply(plan["plan_id"])
    assert result["status"] == "succeeded"
    replies = [r for r in setup.drive.comment_threads["doc"][0]["replies"] if r["content"] == "+1"]
    assert len(replies) == 2
    assert result["results"][0]["reply_id"] != result["results"][1]["reply_id"]


def test_file_losing_comment_permission_is_rechecked_on_apply(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("doc", [{"op": "add", "content": "x"}])
    setup.drive.resources["doc"] = replace(setup.drive.resources["doc"], capabilities={"canComment": False})
    with pytest.raises(HarnessError) as raised:
        setup.apply(plan["plan_id"])
    assert raised.value.code == "insufficient_capability"


def test_replaying_a_succeeded_plan_does_not_duplicate_anything(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.preview("doc", [{"op": "add", "content": "Nuevo comentario"}])
    first = setup.apply(plan["plan_id"])
    assert first.get("replayed") is not True
    second = setup.apply(plan["plan_id"])
    assert second["replayed"] is True
    matching = [c for c in setup.drive.comment_threads["doc"] if c["content"] == "Nuevo comentario"]
    assert len(matching) == 1
