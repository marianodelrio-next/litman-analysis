"""Previewed, duplicate-free comment changes (add, reply, resolve) on one file of the dossier.

Comments are unanchored: Drive comment anchors are not reliably rendered in
Google Docs, and a comment carries no marker a resume could search for.
Instead, each action's preview stores the newest ``createdTime`` Drive showed
among the file's comments and replies (``created_after``); on resume, an
existing comment or reply by the active account (``author.me``) with the same
content and a later ``createdTime`` is adopted instead of creating a second
one. More than one such candidate is ambiguous and ends as a conflict.
"""
from __future__ import annotations

from typing import Any

from ..errors import HarnessError
from ..plans.models import Plan, PlanAction
from .membership import belongs_to_root, in_litman
from .service import ExpedienteService, OperationConflict, OperationRun
from .models import Resource

MAX_OPERATIONS = 10
MAX_CONTENT_CHARS = 4096
OPERATIONS = {"add": frozenset({"content"}), "reply": frozenset({"comment_id", "content"}),
             "resolve": frozenset({"comment_id"})}
_OPTIONAL = {"resolve": frozenset({"content"})}


def _invalid(message: str, **details: Any) -> HarnessError:
    return HarnessError("invalid_request", message, details=details)


def validated_operations(operations: Any) -> list[dict[str, Any]]:
    """1-10 closed operations with exact fields; checked here because transports validate only top-level types."""
    if not isinstance(operations, list) or not 1 <= len(operations) <= MAX_OPERATIONS:
        raise _invalid(f"Indique entre 1 y {MAX_OPERATIONS} operaciones")
    clean = []
    for index, operation in enumerate(operations):
        kind = operation.get("op") if isinstance(operation, dict) else None
        if kind not in OPERATIONS:
            raise _invalid("Operación no admitida", operation=index, allowed=list(OPERATIONS))
        required, optional = OPERATIONS[kind], _OPTIONAL.get(kind, frozenset())
        present = set(operation) - {"op"}
        if not (required <= present <= required | optional):
            raise _invalid(f"La operación {kind} lleva op y " + ", ".join(sorted(required)) +
                           ("".join(f" y opcionalmente {name}" for name in sorted(optional))),
                           operation=index)
        entry: dict[str, Any] = {"op": kind}
        if "comment_id" in present:
            value = operation["comment_id"]
            if not isinstance(value, str) or not value:
                raise _invalid("comment_id debe ser texto no vacío", operation=index)
            entry["comment_id"] = value
        if "content" in present:
            value = operation["content"]
            if not isinstance(value, str) or not 1 <= len(value) <= MAX_CONTENT_CHARS:
                raise _invalid(f"content debe ser texto de 1 a {MAX_CONTENT_CHARS} caracteres", operation=index)
            entry["content"] = value
        clean.append(entry)
    return clean


def _is_mine(raw: dict[str, Any]) -> bool:
    author = raw.get("author")
    return isinstance(author, dict) and bool(author.get("me"))


def _latest_created(comments: list[dict[str, Any]]) -> str | None:
    """The newest ``createdTime`` Drive showed among the file's comments and its non-deleted replies."""
    stamps = [comment.get("createdTime") for comment in comments if isinstance(comment.get("createdTime"), str)]
    stamps += [reply.get("createdTime") for comment in comments for reply in (comment.get("replies") or [])
              if not reply.get("deleted") and isinstance(reply.get("createdTime"), str)]
    return max(stamps) if stamps else None


class CommentService:
    def __init__(self, dossier: ExpedienteService):
        self.dossier = dossier
        self.drive = dossier.drive

    # -- plan ------------------------------------------------------------------------------------

    def preview(self, folder_id: str, file_id: str, operations: list[dict[str, Any]]) -> dict[str, Any]:
        """Resolve 1-10 closed comment operations on one file and store a ``comment_changes`` plan."""
        clean = validated_operations(operations)
        root = self.dossier.root(folder_id)
        account = self.dossier.account_id()
        item = self._resolve(root, file_id)
        if not item.capabilities.get("canComment", False):
            raise HarnessError("insufficient_capability", "La cuenta no puede comentar este archivo",
                               details={"file_id": item.id})
        current = [comment for comment in self.drive.comments(item.id) if isinstance(comment, dict)]
        by_id = {comment["id"]: comment for comment in current if comment.get("id")}
        created_after = _latest_created(current)
        actions = []
        for index, entry in enumerate(clean):
            comment_id = entry.get("comment_id")
            if comment_id is not None and comment_id not in by_id:
                raise HarnessError("comment_not_found", "El comentario no existe o está eliminado",
                                   details={"operation": index, "comment_id": comment_id})
            # ``parent_id`` carries the plan-local index, not the comment_id: two operations can share
            # kind, file and content (e.g. two identical "add"), and action_id() (dossier/service.py)
            # hashes kind/resource_id/parent_id/name only, so a shared comment_id there would collapse
            # them into the same action. The real comment_id, if any, lives in metadata instead.
            actions.append(PlanAction(entry["op"], item.id, entry.get("content") or "", str(index),
                                      metadata={"index": index, "created_after": created_after,
                                                "comment_id": comment_id}))
        plan = Plan("comment_changes", root.id, account, tuple(actions), {})
        self.dossier.store().save(plan)
        previews = [{"op": entry["op"], "comment_id": entry.get("comment_id"),
                    "quoted_text": by_id.get(entry.get("comment_id"), {}).get("content")}
                   for entry in clean]
        return {**plan.json(), "file_id": item.id, "operations": previews}

    def apply(self, accepted_plan_id: str) -> dict[str, Any]:
        return self.dossier.apply_plan(accepted_plan_id, "comment_changes", self._run)

    # -- apply -----------------------------------------------------------------------------------

    def _run(self, run: OperationRun, root: Resource) -> dict[str, Any]:
        # Every comment/reply ID a prior action of this same plan already claimed (completed now or
        # before an interruption): excluded from resume matching so one of them never satisfies two
        # actions with identical content.
        claimed = {identifier for action in run.plan.actions if run.done(action)
                  for identifier in run.output(action).values() if isinstance(identifier, str)}
        for action in run.plan.actions:
            if run.done(action):
                continue
            item = self._resolve(root, action.resource_id)
            if not item.capabilities.get("canComment", False):
                raise HarnessError("insufficient_capability", "La cuenta ya no puede comentar este archivo",
                                   details={"file_id": item.id})
            handler = getattr(self, f"_apply_{action.kind}")
            output = handler(run, item, action, claimed)
            run.complete(action, output)
            claimed.update(value for value in output.values() if isinstance(value, str))
        return run.envelope("succeeded", writes=True, results=[run.output(a) for a in run.plan.actions])

    def _apply_add(self, run: OperationRun, item: Resource, action: Any, claimed: set[str]) -> dict[str, Any]:
        current = [comment for comment in self.drive.comments(item.id) if isinstance(comment, dict)]
        match = self._resume_match(run, action, current, claimed)
        if match is not None:
            return {"comment_id": match["id"]}
        created = self.drive.create_comment(item.id, action.name)
        return {"comment_id": created["id"]}

    def _apply_reply(self, run: OperationRun, item: Resource, action: Any, claimed: set[str]) -> dict[str, Any]:
        comment_id = action.metadata["comment_id"]
        comment = self._find_comment(item, comment_id)
        replies = [reply for reply in (comment.get("replies") or []) if not reply.get("deleted")
                  and not reply.get("action")]
        match = self._resume_match(run, action, replies, claimed)
        if match is not None:
            return {"comment_id": comment_id, "reply_id": match["id"]}
        created = self.drive.create_reply(item.id, comment_id, action.name)
        return {"comment_id": comment_id, "reply_id": created["id"]}

    def _apply_resolve(self, run: OperationRun, item: Resource, action: Any, claimed: set[str]) -> dict[str, Any]:
        comment_id = action.metadata["comment_id"]
        comment = self._find_comment(item, comment_id)
        if comment.get("resolved"):
            return {"comment_id": comment_id, "reply_id": None}
        replies = [reply for reply in (comment.get("replies") or []) if not reply.get("deleted")
                  and reply.get("action") == "resolve"]
        match = self._resume_match(run, action, replies, claimed)
        if match is not None:
            return {"comment_id": comment_id, "reply_id": match["id"]}
        created = self.drive.create_reply(item.id, comment_id, action.name, action="resolve")
        return {"comment_id": comment_id, "reply_id": created["id"]}

    def _find_comment(self, item: Resource, comment_id: str) -> dict[str, Any]:
        comment = next((comment for comment in self.drive.comments(item.id) if comment.get("id") == comment_id),
                       None)
        if comment is None:
            raise HarnessError("comment_not_found", "El comentario ya no existe", details={"comment_id": comment_id})
        return comment

    def _resume_match(self, run: OperationRun, action: Any, candidates: list[dict[str, Any]],
                      claimed: set[str]) -> dict[str, Any] | None:
        created_after = action.metadata.get("created_after")
        matches = [candidate for candidate in candidates
                  if candidate.get("id") not in claimed and _is_mine(candidate)
                  and candidate.get("content", "") == action.name and isinstance(candidate.get("createdTime"), str)
                  and (created_after is None or candidate["createdTime"] > created_after)]
        if len(matches) > 1:
            raise OperationConflict("Hay más de un candidato para reanudar esta acción sin duplicarla",
                                    details={"operation": action.metadata["index"], "completed": list(run.completed)})
        return matches[0] if matches else None

    # -- shared helpers ----------------------------------------------------------------------------

    def _resolve(self, root: Resource, file_id: str) -> Resource:
        """A file inside the tree and not at or below ``_LitMan``, checked before reading or writing its comments."""
        item = self.drive.get(file_id)
        if item.id != root.id and (not belongs_to_root(self.drive, root, item) or in_litman(self.drive, root, item)):
            raise HarnessError("document_outside_tree", "El archivo no está dentro de la licitación conectada",
                               details={"file_id": file_id})
        return item
