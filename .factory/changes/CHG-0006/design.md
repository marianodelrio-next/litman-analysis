# CHG-0006 — Read, edit and create Google Docs of a dossier through LitMan tools

## Context
Verified on `master` at `e37b710`:

- In a real Windows run with the Codex app, the person asked the assistant to change text in the
  technical proposal. That proposal is the live offer: the Google Doc that publication creates in
  `Oferta` by converting Core's technical DOCX (`dossier/publication.py`, `convert_live_offer`).
  LitMan has no edit operation, so the assistant fell back to computer use in the browser. No
  earlier design for document editing exists in the repository or in its history: the old
  `.agent-work/` "tarea 05" notes are gone and were never implemented.
- **Tool registry:** `harness/src/litman_harness/interfaces/tools/__init__.py` (`Tool`, `schema`,
  `registry()`, `validate_arguments`). `validate_arguments` checks top-level types, enums and array
  items only; it does not check nested object fields or `oneOf`. The dossier tools live in
  `interfaces/tools/dossier.py`.
- **Mutation model:** every mutation is a `preview_*` that stores an account-bound `Plan`
  (`plans/models.py`, `plans/store.py`), followed by an `apply_*` that runs through
  `ExpedienteService.apply_plan()` (`dossier/service.py`). `apply_plan()` provides:
  - replay of a finished operation (`replayed: true`, `writes: false`);
  - `pending_concurrency_gate` on the read-only metadata adapter;
  - `OperationConflict`, recorded as `status: "conflict"`;
  - interruptions recorded as `RECOVERABLE`, with an `OperationRun` keeping `completed` and
    `outputs`.
  
  `_verify_snapshot()` returns early for every kind except `incorporation`. Created resources carry
  `litman_operation_id`/`litman_action_id` markers and are adopted with `ensure_marked()`.
- **`read_document`** (`dossier/summary.py`, `SummaryService.read_document`):
  - it requires an adopted dossier;
  - it reads only IDs from `Manifest.summary_sources()`, and unregistered IDs never reach Drive;
  - it reads only PDF and DOCX files;
  - it returns pages of `PAGE_SIZE = 20_000` characters with `CONTENT_NOTE`.
  
  `tests/dossier/test_summary.py` (`test_read_document_rejects_unregistered_outside_and_unsupported`)
  expects the Google Doc `offer-doc` to be rejected with `document_not_registered`. This change does
  **not** alter `read_document`.
- **OAuth:** it requests only `https://www.googleapis.com/auth/drive` (`adapters/oauth.py`,
  `SCOPES`). `DesktopOAuthProvider.drive_service()` builds `build("drive", "v3", …)`.
  `interfaces/assembly.py` `build_services()` wires one `GoogleDriveGateway`, and `Services` has no
  Docs client. Google's scope list for the Docs API v1 includes `drive` for `documents.get` and
  `documents.batchUpdate`; this still has to be confirmed on the real project. The Docs API must be
  enabled once in the Google Cloud project that owns the OAuth client (the `client_secret.json`
  delivered to employees, `harness/deployment/README.md`).
- **Dependencies:** `google-api-python-client` is already a dependency and ships the Docs v1
  discovery document, so no new dependency is needed. `tests/adapters/test_drive_adapter.py`
  (`test_gateway_calls_match_the_real_drive_v3_discovery_document`) shows how to build a real client
  offline with `static_discovery=True` and `HttpMockSequence`.
- **Membership and `_LitMan`:** membership is `dossier/membership.py` `belongs_to_root()`. The tree
  walk (`dossier/tree.py`, `LITMAN_FOLDER = "_LitMan"`) never descends into any folder named
  `_LitMan`.
- **Product resources that steer the assistant:**
  - `harness/agent/skills/conectar-licitacion/SKILL.md`
  - `harness/agent/workspace/AGENTS.md`
  - `harness/agent/skills/preparar-equipo/SKILL.md`
  
  Their tool references are checked by `harness/tests/interfaces/test_agent_files.py`. The person
  explicitly asked for these instructions to change.

## Goal and scope
In scope:
- The assistant can read any native Google Doc inside the connected dossier.
- It can change the document's body text through a previewed and accepted plan with revision
  control.
- It can create new Google Docs in a dossier folder, from text or by converting a DOCX that is in
  the dossier.
- The instructions tell the assistant to use these tools, and never computer use or a browser, for
  Drive documents.

Out of scope:
- editing DOCX or PDF in place (a DOCX is edited by first creating a converted Google Doc);
- formatting (styles, headings, tables, images);
- comments and accepting or rejecting suggestions;
- headers, footers and documents with more than one tab;
- registering created documents in the manifest or in `contexto.md`;
- changing `read_document` or the live-offer rules;
- Core and the summary contract.

## Acceptance criteria
- AC-01: Given a Google Doc anywhere in the dossier tree, when the new query `read_google_doc`
  (`folder_id`, `document_id`, `offset`) is called, then it returns:
  - the body's visible text, paged like `read_document`;
  - `revision_id` (or `null`);
  - `CONTENT_NOTE` and `writes: false`.
  
  It is rejected with no content read when the file is outside the tree, below a `_LitMan` folder,
  or not a Google Doc (`unsupported_document`). `read_document` behaviour is unchanged (the existing
  `test_summary.py` tests still pass unmodified) — verified by: tests in the new
  `harness/tests/dossier/test_documents.py`.
- AC-02: Given `preview_document_edit(folder_id, document_id, operations)` with 1–20 operations from
  the closed set below, when previewed, then a plan is stored and returned with the document's
  `revision_id` and, for each operation, the matched span with up to 80 characters of context before
  and after. The closed set is:
  - `replace_text {find, replace, occurrences}`
  - `insert_after {anchor, text}`
  - `append {text}`
  
  The preview fails without storing a plan in each of these cases:
  - `occurrences` is not the real count (`occurrences_mismatch`, with the real count);
  - an anchor is missing or not unique (`anchor_not_unique`);
  - `find` or `anchor` is empty or contains a newline (`invalid_request`);
  - two operations' spans overlap, or two inserts use the same anchor (`overlapping_operations`);
  - after simulating the request order, the expected text does not contain each `replace` exactly
    `occurrences` times at the planned positions (`overlapping_operations`);
  - a span touches a pending suggestion (`pending_suggestions`);
  - the document has more than one tab (`unsupported_document`);
  - `revision_id` is null or Drive reports `canEdit: false` (`insufficient_capability`);
  - the file is not a Google Doc of the dossier.
  
  — verified by: tests in `test_documents.py`.
- AC-03: Given an accepted edit plan, when `apply_document_edit` runs, then it re-checks membership,
  MIME and `canEdit`, and sends exactly one `documents.batchUpdate`. That request carries
  `writeControl.requiredRevisionId` equal to the preview's revision and contains only index-based
  `deleteContentRange`/`insertText` requests on the body. The resulting body text equals the plan's
  expected text, including documents with accented characters and characters outside the BMP —
  verified by: tests against a fake Docs service, plus one test that builds the real Docs v1 client
  offline (`static_discovery=True`, `HttpMockSequence`) so the request shapes are validated by the
  discovery schema.
- AC-04: Each of these cases is verified by a test in `test_documents.py`:
  - **Concurrent edit:** given a document changed after the preview (any 400 response to a request
    with `requiredRevisionId`), when the plan is applied, then the result is `status: "conflict"`
    with code `document_changed` and nothing is written.
  - **Lost answer:** given an apply whose `batchUpdate` succeeded but whose answer was lost (the run
    is `RECOVERABLE`), when the acceptance is repeated and the body equals the expected text, then
    the operation succeeds without a second `batchUpdate`.
  - **Replay:** repeating a succeeded plan returns `replayed: true`.
- AC-05: Given `preview_document_creation(folder_id, parent_folder_id, name, text | source_file_id)`
  with exactly one of `text` or `source_file_id` (checked in the service), when applied, then a
  Google Doc named `name` is created in `parent_folder_id` with markers. It contains `text`, or the
  converted content of the dossier DOCX `source_file_id`. The preview rejects:
  - a parent that is not a folder of the dossier, or that is a `_LitMan` folder;
  - a source that is not a DOCX of the dossier;
  - a `name` already used in the parent (`name_exists`, checked again at apply).
  
  After an interruption right after the document was created, repeating the acceptance leaves one
  document containing the text once — verified by: tests in `test_documents.py`.
- AC-06: Given a Docs API response 403 whose reason is `accessNotConfigured` or `SERVICE_DISABLED`,
  when any Docs call is made, then the error is `docs_api_disabled`, with a Spanish message saying
  that the administrator must enable the Google Docs API for the OAuth client's project — verified
  by: adapter tests in `tests/adapters/test_docs_adapter.py`.
- AC-07: `diagnose` reports `docs_api` as `enabled`, `disabled` or `unknown`, and never fails
  because of it — verified by: tests in `tests/interfaces`.
- AC-08: All five new operations are registered for CLI and MCP with schemas: `read_google_doc`,
  `preview_document_edit`, `apply_document_edit`, `preview_document_creation` and
  `apply_document_creation` — verified by: `tests/interfaces/test_tools.py` and
  `test_transports.py`.
- AC-09: `conectar-licitacion` and the workspace `AGENTS.md` tell the assistant to:
  - read with `read_google_doc`;
  - edit with `preview_document_edit`/`apply_document_edit`;
  - create with `preview_document_creation`/`apply_document_creation`;
  - show the preview and apply only what the person accepts;
  - never use computer use or a browser to change Drive documents.
  
  `preparar-equipo` covers the `docs_api` check — verified by: `tests/interfaces/test_agent_files.py`.
- AC-10: These documents describe the feature — verified by: manual conformance review:
  - `harness/docs/architecture.md`, `decisions.md` and `operations.md`;
  - `harness/deployment/README.md` (enable the Docs API once);
  - `docs/guia-litman-windows.md`;
  - `docs/windows-codex-validation.md`, with a manual step on the real account: read, edit,
    conflict and create.
- AC-11: The harness suite passes — verified by:
  `bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'`.

## Approach
- **One index model for every operation.** All spans are computed against the text read at
  preview. `replace_text` becomes, for each counted match, `deleteContentRange` followed by
  `insertText` at the same index. `insert_after` becomes `insertText` at the anchor's end index.
  `append` becomes `insertText` just before the body's final newline (the last paragraph's
  `endIndex - 1`). Spans must be disjoint, and requests are sent in descending index order, so
  earlier indexes are unaffected. The preview simulates exactly that request list on the text and
  stores the expected result in the plan.
  
  `replaceAllText` was rejected: it matches case-insensitively by default, it reaches every tab,
  header and footer, and it cannot be limited to the counted matches.
- **Other alternatives rejected:**
  - Export to DOCX, edit locally and re-upload: destroys formatting, comments and revision history,
    and breaks the live-offer ID.
  - Free-form Docs requests from the assistant: no deterministic preview and no safety boundary.
  - Computer use (what happened): unreliable, and outside LitMan's acceptance model.
- **Suggestions:** read with `suggestionsViewMode="SUGGESTIONS_INLINE"` so that the indexes match
  the document. Text that carries `suggestedInsertionIds` is left out of what is shown, and an
  operation span that touches text with `suggestedInsertionIds` or `suggestedDeletionIds` is
  refused.
- **Revisions:**
  - `requiredRevisionId` guards the write. Revision IDs are valid for only 24 hours, so an old plan
    simply ends in `document_changed`.
  - A lost answer is resolved on resume by comparing the current body with the expected text.
- **Creation from a DOCX** reuses the path that publication already uses (`drive.download` to a
  temporary file, then `drive.upload_converted`), instead of a new `files.copy` conversion.
- **Decision log:** add "Document edits use closed index-based operations guarded by the Docs
  revision" to `harness/docs/decisions.md`.

## Implementation notes
**CHG-0006-01 (Docs adapter, read, edit).**
- **New `harness/src/litman_harness/adapters/docs.py`.** It defines a `DocsGateway` protocol with
  `get(document_id) -> dict` and
  `batch_update(document_id, requests, required_revision_id) -> dict`.
  - `get` calls `documents().get(documentId=…, suggestionsViewMode="SUGGESTIONS_INLINE")`; if the
    discovery document allows it, restrict `fields` to `revisionId`, `body`, `tabs` (enough to
    count the tabs) and `suggestionsViewMode`.
  - HTTP errors are translated by a Docs-specific function next to `adapters/drive.py`
    `http_error()`, so messages say "Google Docs":
    - a 403 with reason `accessNotConfigured`/`SERVICE_DISABLED` becomes `docs_api_disabled`;
    - any 400 on a `batch_update` becomes `document_changed`;
    - 401/403/404 otherwise map as Drive's do.
  - Parse the `HttpError` content JSON (`error.errors[].reason` or
    `error.details[].reason`); test with payloads of that shape.
- **Wiring:**
  - `DesktopOAuthProvider.docs_service()` mirrors `drive_service()` with `build("docs", "v1", …)`.
  - Add `docs` and `documents` (the service) to `Services` in `interfaces/assembly.py`.
  - The metadata adapter gets a Docs gateway whose methods raise the same read-only error that
    `MetadataGateway` writes raise.
- **New `harness/src/litman_harness/dossier/documents.py`, `DocumentService(dossier, docs)`.**
  Follow `SummaryService`: use `dossier.root()`, `belongs_to_root()`, `dossier.store()` and
  `dossier.apply_plan()`. One helper `_resolve(root, document_id)`:
  1. one Drive `get`;
  2. `belongs_to_root` (else `document_outside_tree`);
  3. no ancestor folder, from the item up to the root, is named `LITMAN_FOLDER` (else
     `document_outside_tree`);
  4. `mime_type == GOOGLE_DOC_MIME` (else `unsupported_document`).
  
  The adoption state is not required.
- **Text model:**
  - Walk `body.content` in order. Paragraphs contribute their `elements[].textRun.content`. Tables
    are walked by rows, then cells, then the cells' content, recursively. `sectionBreak`,
    `tableOfContents` and non-text paragraph elements (inline objects, page breaks and so on)
    contribute nothing and end the current run.
  - Keep a list of runs `(text_offset, doc_start_index, text, paragraph_id, suggested)`.
  - Docs indexes count UTF-16 code units: compute index offsets inside a run with
    `len(s.encode("utf-16-le")) // 2`. Never assume that one Python character equals one index.
  - An anchor or a `find` must fall within one paragraph.
  - Inserted `text` may contain `\n`; each `\n` starts a new paragraph that inherits the style of the
    paragraph it lands in.
  - `append` text is inserted before the final newline, so it continues the last paragraph unless
    it starts with `\n`. Document this in the tool description.
- **Plans:**
  - Plan kind `"document_edit"`, with one `PlanAction("edit_document", document_id, name, None,
    expected_version=revision_id, metadata={"requests": […], "operations": […],
    "expected_sha256": …})`.
  - Store only the hash of the expected text (and its length), not the text itself, to keep plans
    small.
  - The apply runner re-runs `_resolve`, checks `canEdit`, and when the run has a previous
    `RECOVERABLE` attempt (`run.output(action)` was noted before the call), reads the document and
    completes the action if the body hash equals `expected_sha256`. Otherwise it sends the batch.
  - `document_changed` from the adapter is raised as `OperationConflict`, so `apply_plan` records a
    conflict.
  - Call `run.note(action, {"sent": True})` just before `batch_update` and `run.complete` after it.
- **Validation** of operation shapes (keys, types, lengths, 1–20 items) happens in the service,
  because `validate_arguments` does not check nested objects.
- **Tools:** add a new `interfaces/tools/documents.py` with `read_google_doc`,
  `preview_document_edit` and `apply_document_edit` (`mutates=True`, `_GATE` text), and register it
  in `registry()`.
- **Fakes in `tests/fakes.py`:** `FakeDocs` holds one structural document per ID (paragraphs, one
  table, optional suggestion runs, `tabs`) with a `revisionId` that changes on every write, and
  implements `deleteContentRange` and `insertText` (location index and `endOfSegmentLocation` are
  not needed) by UTF-16 index. It can be told to lose the answer after applying a batch. Adapter
  tests go in the new `tests/adapters/test_docs_adapter.py`, following
  `tests/adapters/test_drive_adapter.py`, including the offline discovery test.

**CHG-0006-02 (creation).**
- **Drive gateway:** add `create_document(name, parent_id, operation_id, action_id)`, which calls
  `files().create` with `mimeType: GOOGLE_DOC_MIME`, `parents` and markers. Mirror it in `FakeDrive`
  (through `_create`) and in `MetadataGateway` (read-only error). For a DOCX source, use
  `drive.download` to a `tempfile.TemporaryDirectory()` followed by `drive.upload_converted` (the
  existing method).
- **Plan kind `"document_creation"`**, with actions:
  - `create_document` or `convert_document`, adopted with `ensure_marked` on the parent;
  - for text, `write_initial_text`. On resume, skip it if the body already equals the text, insert
    the text if the body is empty, and return a conflict otherwise.
  
  `name_exists` is checked again at apply, ignoring the resource carrying this action's markers.
- **Tools** `preview_document_creation` and `apply_document_creation` go in
  `interfaces/tools/documents.py`. The result returns the new `document_id` and `web_view_link`.

**CHG-0006-03 (diagnose, instructions, docs).**
- **`assembly.diagnose()`:** add `docs_api` by calling the Docs gateway `get` on a fixed ID that
  does not exist:
  - 404 → `enabled`;
  - `docs_api_disabled` → `disabled`;
  - anything else, or no credentials → `unknown`.
  
  Wrap the call so that diagnose never fails because of it.
- **Instructions:** update `conectar-licitacion/SKILL.md`, `workspace/AGENTS.md` and
  `preparar-equipo/SKILL.md` in Spanish, in the existing tone, and extend `test_agent_files.py`.
- **Documentation:** the files listed in AC-10. The user-facing guide text stays in Spanish
  (`guia-litman-windows.md`); developer docs are in English.

## Tasks
```yaml
- id: CHG-0006-01
  title: Read and edit dossier Google Docs through the Docs API with previewed, revision-guarded plans
  depends_on: []
  complexity: complex
  review: [quality, conformance]
  scope: ["harness/src/litman_harness/**", "harness/tests/**"]
  acceptance:
    AC-01: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier'"
    AC-02: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_documents.py'"
    AC-03: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_documents.py tests/adapters/test_docs_adapter.py'"
    AC-04: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_documents.py'"
    AC-06: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/adapters/test_docs_adapter.py'"
    AC-08: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/interfaces'"
    AC-11: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'"
- id: CHG-0006-02
  title: Create dossier Google Docs from text or by converting a dossier DOCX
  depends_on: [CHG-0006-01]
  complexity: normal
  review: [quality, conformance]
  scope: ["harness/src/litman_harness/**", "harness/tests/**"]
  acceptance:
    AC-05: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_documents.py tests/adapters'"
    AC-08: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/interfaces'"
    AC-11: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'"
- id: CHG-0006-03
  title: Docs API diagnosis, assistant instructions and documentation for document tools
  depends_on: [CHG-0006-01, CHG-0006-02]
  complexity: normal
  review: [quality, conformance]
  scope: ["harness/src/litman_harness/interfaces/**", "harness/agent/**", "harness/tests/**", "harness/docs/**", "harness/deployment/README.md", "docs/guia-litman-windows.md", "docs/windows-codex-validation.md"]
  acceptance:
    AC-07: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/interfaces'"
    AC-09: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/interfaces/test_agent_files.py'"
    AC-10: manual
    AC-11: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'"
```

## Risks and open questions
- **To confirm on the real project** (the manual step in AC-10):
  - the Docs API accepts the existing `drive`-scope token; if it were rejected, adding the
    `documents` scope would force every employee to log in again;
  - the exact error payloads for a disabled API and for a stale revision;
  - that `revisionId` is returned to the person's role.
- **Enabling the Docs API:** whoever administers the OAuth client's Cloud project must enable it
  once; until then the tools return `docs_api_disabled`.
- **Formatting:** inserted text takes the style of the paragraph where it lands; this version
  creates no headings or tables.
- **Merges:** CHG-0004 and CHG-0005 also touch `tests/fakes.py`, `adapters/drive.py`,
  `adapters/metadata.py` and the Windows guides; expect small merges if they run in parallel.
