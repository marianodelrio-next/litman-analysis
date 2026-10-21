"""Previewed, duplicate-free comment changes (add, reply, resolve) on one file of the dossier.

Every new comment is a native Google Docs comment anchored to one exact phrase
of the document (``add`` takes ``anchor``); no general, unanchored comment is
ever created.  The native operations of a plan travel in one ``documents.batchUpdate``
(``docs_comment_batch``) guarded by the revision of the preview, and they are
only reported as done once a read-back shows them: the thread with its live
anchor, the reply post or the resolved state.  Google offers no idempotency key,
so after a sent attempt with no provable result the operation stays
``comment_write_uncertain`` and a retry only reconciles, it never sends again.

Native threads are routed by the opaque ID ``docs:<id>``; a historical Drive
comment keeps its raw ID and its reply/resolve operations still go through
Drive, resumed as before: each action stores the newest ``createdTime`` Drive
showed (``created_after``) and a resume adopts the active account's reply with
the same content and a later ``createdTime``.  An unfinished legacy ``add``
(unanchored) is refused before any write.
"""
from __future__ import annotations

from typing import Any

from ..errors import HarnessError
from ..plans.models import Plan, PlanAction
from .documents import (MAX_MATCH_CHARS, DocumentService, DocumentText, anchor_selection, first_tab_id,
                        parse_document)
from .membership import belongs_to_root, in_litman
from .service import ExpedienteService, OperationConflict, OperationRun
from .models import GOOGLE_DOC_MIME, Resource

MAX_OPERATIONS = 10
MAX_CONTENT_CHARS = 4096  # Drive replies to historical comments
MAX_NATIVE_CONTENT_BYTES = 2048  # Docs comments and replies, in UTF-8 bytes
MAX_ANCHOR_CHARS = MAX_MATCH_CHARS
NATIVE_PREFIX = "docs:"
OPERATIONS = {"add": frozenset({"content", "anchor"}), "reply": frozenset({"comment_id", "content"}),
              "resolve": frozenset({"comment_id"})}
_OPTIONAL = {"resolve": frozenset({"content"})}
_PLAIN_ACTIONS = (None, "COMMENT_ACTION_TYPE_UNSPECIFIED", "NO_COMMENT_ACTION_CHANGE")
_ANCHOR_REQUIRED = ("Este plan aceptado añade un comentario general sin ancla, que ya no se admite. No se ha escrito "
                    "nada de lo pendiente: prepare un plan nuevo con preview_comment_changes en el que cada add "
                    "lleve el fragmento exacto del documento (anchor).")


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
        if "anchor" in present:
            value = operation["anchor"]
            if not isinstance(value, str) or not 1 <= len(value) <= MAX_ANCHOR_CHARS:
                raise _invalid(f"anchor debe ser texto de 1 a {MAX_ANCHOR_CHARS} caracteres", operation=index)
            entry["anchor"] = value
        clean.append(entry)
    return clean


def is_native(operation: dict[str, Any]) -> bool:
    """A new comment or an operation on a ``docs:`` thread goes through Google Docs; the rest through Drive."""
    return operation["op"] == "add" or operation.get("comment_id", "").startswith(NATIVE_PREFIX)


def _is_mine(raw: dict[str, Any]) -> bool:
    author = raw.get("author")
    return isinstance(author, dict) and bool(author.get("me"))


def _native_mine(post: dict[str, Any]) -> bool:
    author = post.get("author")
    return isinstance(author, dict) and bool(author.get("me"))


def _threads(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {thread["commentId"]: thread for thread in raw.get("comments") or []
            if isinstance(thread, dict) and isinstance(thread.get("commentId"), str)}


def _anchors(raw: dict[str, Any]) -> dict[str, tuple[str | None, list[dict[str, Any]]]]:
    """Every tab's comment anchors: anchor ID → (tab ID, ranges)."""
    found = {}
    for tab in raw.get("tabs") or []:
        tab_id = (tab.get("tabProperties") or {}).get("tabId")
        for anchor_id, anchor in ((tab.get("documentTab") or {}).get("commentAnchors") or {}).items():
            ranges = [item for item in (anchor or {}).get("ranges") or [] if isinstance(item, dict)
                      and isinstance(item.get("startIndex"), int) and isinstance(item.get("endIndex"), int)]
            found[anchor_id] = (tab_id, ranges)
    return found


def _posts(thread: dict[str, Any]) -> list[dict[str, Any]]:
    return [post for post in thread.get("replies") or [] if isinstance(post, dict) and not post.get("deleted")]


def _newest(threads: dict[str, dict[str, Any]]) -> str | None:
    """The newest ``createTime`` among the native threads and their posts, the server's own clock."""
    stamps = [post.get("createTime") for thread in threads.values()
              for post in [thread.get("headPost") or {}, *_posts(thread)]]
    stamps = [stamp for stamp in stamps if isinstance(stamp, str)]
    return max(stamps) if stamps else None


def native_comment(thread: dict[str, Any], anchors: dict[str, tuple[str | None, list[dict[str, Any]]]],
                   document: DocumentText, first_tab: str | None) -> dict[str, Any]:
    """The public view of a native thread: ``docs:`` ID, quoted text and its current anchor, if it still exists."""
    head = thread.get("headPost") or {}
    tab_id, ranges = anchors.get(thread.get("anchorId"), (None, []))
    anchor = None
    if ranges:
        live = "".join(document.span_text(item["startIndex"], item["endIndex"]) for item in ranges)
        anchor = {"tab_id": tab_id, "ranges": [{"start_index": item["startIndex"], "end_index": item["endIndex"]}
                                                for item in ranges],
                  "text": live if tab_id in (None, first_tab) else None}
    return {"id": NATIVE_PREFIX + thread["commentId"], "source": "docs", "content": head.get("content"),
            "author": _author(head), "created_time": head.get("createTime"),
            "resolved": thread.get("status") == "RESOLVED", "quoted_text": thread.get("plainTextQuote"),
            "anchor": anchor,
            "replies": [{"id": post.get("postId"), "content": post.get("content"), "author": _author(post),
                         "created_time": post.get("createTime"),
                         "action": {"RESOLVE": "resolve", "REOPEN": "reopen"}.get(post.get("commentAction"))}
                        for post in _posts(thread)]}


def drive_comment(raw: dict[str, Any]) -> dict[str, Any]:
    quoted = raw.get("quotedFileContent")
    return {"id": raw.get("id"), "source": "drive", "content": raw.get("content"), "author": _author(raw),
            "created_time": raw.get("createdTime"), "resolved": bool(raw.get("resolved")),
            "quoted_text": quoted.get("value") if isinstance(quoted, dict) else None, "anchor": None,
            "replies": [{"id": reply.get("id"), "content": reply.get("content"), "author": _author(reply),
                         "created_time": reply.get("createdTime"), "action": reply.get("action")}
                        for reply in raw.get("replies") or [] if not reply.get("deleted")]}


def _author(raw: dict[str, Any]) -> str | None:
    author = raw.get("author")
    return author.get("displayName") if isinstance(author, dict) else None


def _response_ids(response: dict[str, Any], count: int) -> list[str | None]:
    """The thread or post ID Google returned for each request, ``None`` where it is missing."""
    replies = response.get("replies") if isinstance(response.get("replies"), list) else []
    ids: list[str | None] = []
    for position in range(count):
        reply = replies[position] if position < len(replies) and isinstance(replies[position], dict) else {}
        thread = (reply.get("insertComment") or {}).get("commentThread") or {}
        post = (reply.get("addCommentReply") or {}).get("post") or {}
        value = thread.get("commentId") or post.get("postId")
        ids.append(value if isinstance(value, str) and value else None)
    return ids


def _latest_created(comments: list[dict[str, Any]]) -> str | None:
    """The newest ``createdTime`` Drive showed among the file's comments and its non-deleted replies."""
    stamps = [comment.get("createdTime") for comment in comments if isinstance(comment.get("createdTime"), str)]
    stamps += [reply.get("createdTime") for comment in comments for reply in (comment.get("replies") or [])
              if not reply.get("deleted") and isinstance(reply.get("createdTime"), str)]
    return max(stamps) if stamps else None


class CommentService:
    def __init__(self, dossier: ExpedienteService, documents: DocumentService):
        self.dossier = dossier
        self.drive = dossier.drive
        self.documents = documents
        self.docs = documents.docs

    # -- query -----------------------------------------------------------------------------------

    def listed(self, item: Resource, include_resolved: bool) -> list[dict[str, Any]]:
        """Comments of a file already proved inside the tree: native Docs threads, then historical Drive ones.

        A native thread whose raw ID Drive also lists is shown once, as native; any other Drive comment keeps
        its own raw ID.  A failed native read is an error, never an empty or Drive-only list.
        """
        comments = [drive_comment(raw) for raw in self.drive.comments(item.id) if isinstance(raw, dict)]
        if item.mime_type == GOOGLE_DOC_MIME:
            raw = self.docs.get_with_comments(item.id)
            _, document = parse_document(raw)
            anchors, threads = _anchors(raw), _threads(raw)
            native = [native_comment(thread, anchors, document, first_tab_id(raw)) for thread in threads.values()]
            comments = native + [comment for comment in comments if comment["id"] not in threads]
        return [comment for comment in comments if include_resolved or not comment["resolved"]]

    # -- plan ------------------------------------------------------------------------------------

    def preview(self, folder_id: str, file_id: str, operations: list[dict[str, Any]]) -> dict[str, Any]:
        """Resolve 1-10 closed comment operations on one file and store a ``comment_changes`` plan."""
        clean = validated_operations(operations)
        native = [entry for entry in clean if is_native(entry)]
        if native and len(native) != len(clean):
            raise HarnessError("mixed_comment_backends", "Los comentarios nuevos y los hilos docs: no se mezclan con "
                               "respuestas a comentarios históricos de Drive; prepare un plan para cada grupo",
                               details={"native": [clean.index(entry) for entry in native]})
        root = self.dossier.root(folder_id)
        account = self.dossier.account_id()
        item = self._resolve(root, file_id)
        if native:
            action, previews = self._native_action(item, clean)
            actions: tuple[PlanAction, ...] = (action,)
        else:
            actions, previews = self._drive_actions(item, clean)
        plan = Plan("comment_changes", root.id, account, actions, {})
        self.dossier.store().save(plan)
        return {**plan.json(), "file_id": item.id, "operations": previews}

    def _native_action(self, item: Resource, clean: list[dict[str, Any]]) -> tuple[PlanAction, list[dict]]:
        """One ``docs_comment_batch`` action: every request resolved now, on the revision it was read from."""
        for index, entry in enumerate(clean):
            if len(entry.get("content", "").encode("utf-8")) > MAX_NATIVE_CONTENT_BYTES:
                raise _invalid(f"content de un comentario de Google Docs admite como máximo "
                               f"{MAX_NATIVE_CONTENT_BYTES} bytes en UTF-8", operation=index)
        self._require_native(item)
        raw, document = self._native_read(item)
        revision = raw.get("revisionId")
        if not isinstance(revision, str) or not revision:
            raise HarnessError("insufficient_capability", "La cuenta no puede editar este documento de Google Docs: "
                               "los comentarios nuevos necesitan acceso de edición", details={"file_id": item.id})
        threads, tab_id = _threads(raw), first_tab_id(raw)
        operations, requests, previews = [], [], []
        for index, entry in enumerate(clean):
            if entry["op"] == "add":
                selection = anchor_selection(document, entry["anchor"], index, tab_id)
                span = selection["range"]
                requests.append({"insertComment": {"range": span, "content": entry["content"]}})
                operations.append({"index": index, "op": "add", "content": entry["content"],
                                   "anchor": entry["anchor"], "range": span})
                previews.append({"op": "add", "content": entry["content"], "quoted_text": entry["anchor"],
                                 "tab_id": tab_id, "range": {"start_index": span["startIndex"],
                                                             "end_index": span["endIndex"]},
                                 "context": selection["context"]})
                continue
            thread_id = entry["comment_id"][len(NATIVE_PREFIX):]
            thread = threads.get(thread_id)
            if thread is None:
                raise HarnessError("comment_not_found", "El comentario no existe o está eliminado",
                                   details={"operation": index, "comment_id": entry["comment_id"]})
            post = {"content": entry["content"]} if "content" in entry else {}
            if entry["op"] == "resolve":
                post["commentAction"] = "RESOLVE"
            requests.append({"addCommentReply": {"commentId": thread_id, "post": post}})
            operations.append({"index": index, "op": entry["op"], "content": entry.get("content"),
                               "comment_id": thread_id})
            previews.append({"op": entry["op"], "comment_id": entry["comment_id"], "content": entry.get("content"),
                             "quoted_text": thread.get("plainTextQuote")})
        return PlanAction("docs_comment_batch", item.id, item.name, None, expected_version=revision, metadata={
            "backend": "docs", "operations": operations, "requests": requests}), previews

    def _drive_actions(self, item: Resource, clean: list[dict[str, Any]]) -> tuple[tuple[PlanAction, ...], list]:
        """Reply/resolve actions on historical Drive comments, one per operation."""
        if not item.capabilities.get("canComment", False):
            raise HarnessError("insufficient_capability", "La cuenta no puede comentar este archivo",
                               details={"file_id": item.id})
        current = [comment for comment in self.drive.comments(item.id) if isinstance(comment, dict)]
        by_id = {comment["id"]: comment for comment in current if comment.get("id")}
        created_after = _latest_created(current)
        actions = []
        for index, entry in enumerate(clean):
            comment_id = entry["comment_id"]
            if comment_id not in by_id:
                raise HarnessError("comment_not_found", "El comentario no existe o está eliminado",
                                   details={"operation": index, "comment_id": comment_id})
            # ``parent_id`` carries the plan-local index, not the comment_id: two operations can share
            # kind, file and content (e.g. two identical replies), and action_id() (dossier/service.py)
            # hashes kind/resource_id/parent_id/name only, so a shared comment_id there would collapse
            # them into the same action. The real comment_id lives in metadata instead.
            actions.append(PlanAction(entry["op"], item.id, entry.get("content") or "", str(index),
                                      metadata={"index": index, "created_after": created_after,
                                                "comment_id": comment_id, "backend": "drive"}))
        previews = [{"op": entry["op"], "comment_id": entry["comment_id"],
                     "quoted_text": by_id[entry["comment_id"]].get("content")} for entry in clean]
        return tuple(actions), previews

    def apply(self, accepted_plan_id: str) -> dict[str, Any]:
        return self.dossier.apply_plan(accepted_plan_id, "comment_changes", self._run)

    # -- apply -----------------------------------------------------------------------------------

    def _run(self, run: OperationRun, root: Resource) -> dict[str, Any]:
        # A plan accepted before anchors were required may still hold an unanchored add: refuse the whole
        # remainder before any write, so that the order of its actions cannot bypass the rule.
        unanchored = [action.metadata.get("index") for action in run.plan.actions
                      if action.kind == "add" and not run.done(action)]
        if unanchored:
            raise HarnessError("comment_anchor_required", _ANCHOR_REQUIRED, details={"operations": unanchored})
        if run.plan.actions[0].kind == "docs_comment_batch":
            action = run.plan.actions[0]
            if not run.done(action):
                run.complete(action, self._apply_native(run, root, action))
            return run.envelope("succeeded", writes=True, results=run.output(action)["results"])
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

    # -- native (Google Docs) ----------------------------------------------------------------------

    def _apply_native(self, run: OperationRun, root: Resource, action: PlanAction) -> dict[str, Any]:
        """Send the batch once, then prove each effect by reading the document back."""
        item = self._resolve(root, action.resource_id)
        self._require_native(item)
        state = dict(run.output(action))
        if state.get("sent"):
            # An earlier attempt sent the batch: whatever happened, it is only reconciled, never sent again.
            return self._confirm(run, item, action, state)
        operations = action.metadata["operations"]
        raw, _ = self._native_read(item)
        if raw.get("revisionId") != action.expected_version:
            raise OperationConflict("El documento cambió desde la vista previa; prepare un plan nuevo",
                                    details={"code": "document_changed", "document_id": item.id})
        threads = _threads(raw)
        positions, skipped, requests = [], [], []
        for operation, request in zip(operations, action.metadata["requests"]):
            if operation["op"] != "add":
                thread = threads.get(operation["comment_id"])
                if thread is None:
                    raise OperationConflict("El comentario ya no existe", details={
                        "code": "comment_not_found", "comment_id": NATIVE_PREFIX + operation["comment_id"]})
                if operation["op"] == "resolve" and thread.get("status") == "RESOLVED":
                    skipped.append(operation["index"])
                    continue
            positions.append(operation["index"])
            requests.append(request)
        state = {"sent": True, "positions": positions, "skipped": skipped, "after": _newest(threads),
                 "threads": sorted(threads),
                 "posts": {key: [post.get("postId") for post in _posts(thread)] for key, thread in threads.items()}}
        if not requests:
            return self._confirm(run, item, action, {**state, "response": {"state": "NO_UPDATES_REQUESTED",
                                                                           "ids": []}})
        run.note(action, state)  # the attempt marker, persisted before anything is sent
        try:
            response = self.docs.batch_update_comments(item.id, requests, action.expected_version)
        except HarnessError as exc:
            status = exc.details.get("http_status")
            if exc.code == "document_changed":
                raise OperationConflict(str(exc), details={"code": "document_changed",
                                                           "document_id": item.id}) from exc
            if isinstance(status, int) and 400 <= status < 500:
                run.forget(action)  # Google refused the whole batch: nothing was written
                raise
            raise self._uncertain(run, positions, cause=exc.code) from exc
        except Exception as exc:
            raise self._uncertain(run, positions, cause="no_response") from exc
        state["response"] = {"state": response.get("commentUpdateState"),
                             "ids": _response_ids(response, len(requests))}
        run.note(action, state)
        return self._confirm(run, item, action, state)

    def _confirm(self, run: OperationRun, item: Resource, action: PlanAction,
                 state: dict[str, Any]) -> dict[str, Any]:
        """Each sent operation proved by its returned ID or, failing that, by one unambiguous new candidate."""
        operations = {operation["index"]: operation for operation in action.metadata["operations"]}
        response = state.get("response") or {}
        ids = list(response.get("ids") or [])
        try:
            raw, document = self._native_read(item)
        except HarnessError as exc:
            raise self._uncertain(run, state["positions"], cause=exc.code, response=response) from exc
        threads, anchors = _threads(raw), _anchors(raw)
        claimed = {identifier for identifier in ids if identifier}
        results: dict[int, dict[str, Any]] = {}
        unproved = []
        for position, index in enumerate(state["positions"]):
            operation = operations[index]
            returned = ids[position] if position < len(ids) else None
            pending = [operations[other] for other in state["positions"][position + 1:]
                       if _same_request(operations[other], operation)]
            output = self._observe(run, operation, returned, threads, anchors, document, state, claimed,
                                   1 + len(pending))
            if output is None:
                unproved.append(index)
                continue
            results[index] = output
            claimed.update(value for value in output.values() if isinstance(value, str))
        for index in state["skipped"]:
            results[index] = {"comment_id": operations[index]["comment_id"], "reply_id": None}
        if unproved:
            if response.get("state") == "ALL_FAILED_UNKNOWN_REASON":
                raise HarnessError("comment_save_failed", "Google Docs informó de que no guardó los comentarios y "
                                   "la lectura no muestra todos: no se reenvían. Revise el documento antes de "
                                   "preparar un plan nuevo", details={
                                       "write_may_have_occurred": True, "operations": unproved,
                                       "confirmed": sorted(results), "operation_id": run.plan.operation_id})
            raise self._uncertain(run, unproved, cause="not_observed", response=response,
                                  confirmed=sorted(results))
        return {"results": [_native_output(results[index]) for index in sorted(results)],
                "comment_update_state": response.get("state")}

    def _observe(self, run: OperationRun, operation: dict[str, Any], returned: str | None,
                 threads: dict[str, dict[str, Any]], anchors: dict, document: DocumentText,
                 state: dict[str, Any], claimed: set[str], identical: int) -> dict[str, Any] | None:
        """The proved result of one operation, ``None`` if it cannot be seen; ambiguity is a conflict."""
        index = operation["index"]
        if operation["op"] == "add":
            if returned:
                thread = threads.get(returned)
                if thread is None:
                    return None
                candidates = [thread]
            else:
                candidates = [thread for key, thread in threads.items() if key not in state["threads"]
                              and key not in claimed and _native_mine(thread.get("headPost") or {})
                              and (thread.get("headPost") or {}).get("content") == operation["content"]
                              and _fresh(thread.get("headPost") or {}, state["after"])]
            chosen = self._single(run, index, candidates, identical, lambda t: (t.get("headPost") or {}))
            if chosen is None:
                return None
            if not _anchored(chosen, anchors, document, operation):
                raise OperationConflict("Un comentario guardado no está anclado al fragmento previsto; revíselo en "
                                        "Google Docs", details={"code": "comment_anchor_unverified",
                                                                "operation": index,
                                                                "comment_id": NATIVE_PREFIX + chosen["commentId"],
                                                                "completed": list(run.completed)})
            return {"comment_id": chosen["commentId"]}
        thread = threads.get(operation["comment_id"])
        if thread is None:
            return None
        known = set(state["posts"].get(operation["comment_id"]) or [])
        posts = _posts(thread)
        resolving = operation["op"] == "resolve"
        if returned:
            match = [post for post in posts if post.get("postId") == returned]
        else:
            match = [post for post in posts if post.get("postId") not in known and post.get("postId") not in claimed
                     and _native_mine(post) and _fresh(post, state["after"])
                     and (post.get("commentAction") == "RESOLVE" if resolving
                          else post.get("commentAction") in _PLAIN_ACTIONS)
                     and (resolving and operation.get("content") is None
                          or post.get("content") == operation.get("content"))]
        if resolving:
            # The thread's state is the proof; the resolving post is reported only when it is unambiguous.
            if thread.get("status") != "RESOLVED":
                return None
            post = match[0] if len(match) == 1 else None
            return {"comment_id": operation["comment_id"], "reply_id": post.get("postId") if post else None}
        chosen = self._single(run, index, match, identical, lambda post: post)
        return None if chosen is None else {"comment_id": operation["comment_id"], "reply_id": chosen["postId"]}

    @staticmethod
    def _single(run: OperationRun, index: int, candidates: list[dict[str, Any]], identical: int,
                post_of) -> dict[str, Any] | None:
        """The earliest candidate when there are no more than identical pending operations; more is a conflict."""
        if len(candidates) > identical:
            raise OperationConflict("Hay más de un candidato para reconciliar esta operación sin duplicarla",
                                    details={"operation": index, "candidates": len(candidates),
                                             "completed": list(run.completed)})
        if not candidates:
            return None
        return min(candidates, key=lambda candidate: (post_of(candidate).get("createTime") or "",
                                                      candidate.get("commentId") or candidate.get("postId") or ""))

    @staticmethod
    def _uncertain(run: OperationRun, operations: list[int], *, cause: str | None,
                   response: dict[str, Any] | None = None, confirmed: list[int] | None = None) -> HarnessError:
        return HarnessError("comment_write_uncertain",
                            "No se puede comprobar si Google Docs guardó los comentarios enviados. Puede que se hayan "
                            "escrito: repetir la aceptación sólo vuelve a comprobarlo y nunca los reenvía. Revise el "
                            "documento en Google Docs antes de preparar un plan nuevo",
                            details={"write_may_have_occurred": True, "operation_id": run.plan.operation_id,
                                     "operations": operations, "confirmed": confirmed or [], "cause": cause,
                                     "comment_update_state": (response or {}).get("state")})

    def _require_native(self, item: Resource) -> None:
        if item.mime_type != GOOGLE_DOC_MIME:
            raise HarnessError("unsupported_document", "Los comentarios nuevos sólo se pueden anclar a un fragmento "
                               "de un documento de Google Docs; en otros archivos sólo se responde o resuelve un "
                               "comentario existente", details={"file_id": item.id, "mime_type": item.mime_type})
        if not (item.capabilities.get("canComment", False) and item.capabilities.get("canEdit", False)):
            raise HarnessError("insufficient_capability", "Los comentarios anclados de Google Docs necesitan una "
                               "cuenta con acceso de edición; una cuenta que sólo puede comentar no puede usarlos",
                               details={"file_id": item.id})

    def _native_read(self, item: Resource) -> tuple[dict[str, Any], DocumentText]:
        raw = self.docs.get_with_comments(item.id)
        count, document = parse_document(raw)
        if count != 1:
            raise HarnessError("unsupported_document", "Sólo se puede comentar en documentos de Google Docs con una "
                               "única pestaña", details={"tabs": count})
        return raw, document

    # -- historical Drive comments -----------------------------------------------------------------
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


def _same_request(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return all(first.get(key) == second.get(key) for key in ("op", "content", "anchor", "comment_id"))


def _fresh(post: dict[str, Any], after: str | None) -> bool:
    stamp = post.get("createTime")
    return isinstance(stamp, str) and (after is None or stamp >= after)


def _anchored(thread: dict[str, Any], anchors: dict, document: DocumentText, operation: dict[str, Any]) -> bool:
    """Whether the thread's live anchor still covers exactly the planned phrase (and its quote, if any)."""
    _, ranges = anchors.get(thread.get("anchorId"), (None, []))
    live = "".join(document.span_text(item["startIndex"], item["endIndex"]) for item in ranges)
    quote = thread.get("plainTextQuote")
    return bool(ranges) and live == operation["anchor"] and quote in (None, operation["anchor"])


def _native_output(result: dict[str, Any]) -> dict[str, Any]:
    return {**result, "comment_id": NATIVE_PREFIX + result["comment_id"]}
