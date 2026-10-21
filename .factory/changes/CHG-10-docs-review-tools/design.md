# CHG-10 — Anchored comments, highlighting and links in dossier documents

## Context

The person requested three improvements to the editable Google Doc in `Oferta`:
comments tied to a phrase or section title, text highlighting, and hyperlinks.
They explicitly removed general comment creation from the scope: every new
comment must have a real document anchor. They accepted Google's ordinary link
formatting. They authorized writing this design, not implementation or approval.

Verified against repository head `5e354c083d793b16602398462d73b6a9b57a1b76`:

- `harness/src/litman_harness/dossier/documents.py` already resolves exact text
  matches to UTF-16 indexes, refuses ambiguous/overlapping edits and pending text
  suggestions, and applies accepted plans with `requiredRevisionId`. It supports
  a single document tab and text-only or style-only plans. `set_text_style`
  currently accepts only `bold`, `italic`, and `underline`.
- `dossier/comments.py` creates unanchored Drive comments, replies and resolutions
  in 1–10-operation plans. Its resume matcher uses author, text and creation time;
  it does not resolve document text or inspect a Docs comment anchor.
- `adapters/drive.py:create_comment` sends only `content` to Drive. `dossier/files.py`
  reads comments from Drive, returning `quoted_text` when available.
- `adapters/docs.py` already returns the full batch response, but its document
  getter omits document-level comments and tab comment anchors. Its current HTTP
  mapping treats every write-time 400 as `document_changed`; new requests need
  more precise error handling.
- Style-only recovery in `DocumentService._run_edit` resends on the current revision
  when the text hash is unchanged. Text equality alone does not protect a later
  collaborator's style change. The new format operations must address that case.
- `interfaces/tools/{documents,files}.py` own the shared CLI/MCP tool schemas.
  `interfaces/assembly.py` constructs the Docs and comment services separately.
  Metadata adapters stay read-only. Product instructions live in `harness/agent/`.
- The locked Google client (`google-api-python-client` 2.201.0) includes
  `InsertCommentRequest`, `InsertCommentResponse.commentThread`, comment getters,
  `CommentAnchor`, `PostAuthor.me`, and `commentUpdateState` in its packaged Docs
  v1 discovery document. No new dependency is needed.
- The unchanged Harness baseline passed: `637 passed, 1 skipped`, using
  `UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q` in `harness/`.

### External evidence

Primary sources checked on 2026-10-21; these establish the API contract, not
successful execution against the person's account:

1. [Drive comment constraints](https://developers.google.com/workspace/drive/api/guides/manage-comments):
   Drive custom anchors are not rendered as native text anchors by Workspace
   editors. General comments can be found in the all-comments view. Adding an
   `anchor` string to the existing Drive call is not the solution.
2. [Docs comments and suggestions](https://developers.google.com/workspace/docs/api/how-tos/suggestions):
   native comment creation takes a range; comments and anchors can be read with
   `commentsViewMode=COMMENTS_VIEW_MODE_INCLUDED` and inline suggestions. Comment
   persistence has a separate response status, so HTTP success is insufficient.
3. [Docs request reference](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/request#InsertCommentRequest):
   anchored comment creation has its own content size limit; replies and thread
   resolution use native comment operations.
4. [TextStyle reference](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents#TextStyle):
   background color and link URL are supported style fields. Link changes have
   documented formatting and overlapping-link side effects.
5. [Batch write control](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/batchUpdate):
   required revisions prevent stale writes; the existing Drive OAuth scope is
   accepted. A document revision is exposed only to editors.
6. [Google's release announcement](https://workspaceupdates.googleblog.com/2026/09/programmatic-comment-and-suggestion.html):
   native API comment support was announced on 2026-09-30. Some descriptions in
   the installed discovery schema still carry preview labels. Validate actual
   server support rather than claiming availability from the local schema alone.

## Goal and scope

Enable the following requests on an editable, single-tab Google Doc inside the
connected dossier, outside `_LitMan`:

- Comment on an exact phrase or on the text of a section title.
- Apply, change and remove text highlighting.
- Add, change and remove an HTTP(S) hyperlink on existing text.

All writes use the existing accepted-plan workflow and keep the same document
ID. Comment plans remain separate from text/format edits. New top-level comments
always require an anchor; replying within an existing thread remains supported.
Existing general comments are preserved, readable, replyable and resolvable.

Out of scope: deleting existing comments, retroactively anchoring them, user
assignment/mentions, suggestion-mode edits, multi-tab mutation, table layout,
images, internal heading/bookmark link creation, new document creation features,
Core, analysis generation, DOCX publication and synchronization, dependencies,
OAuth scope expansion, and automatic use of real credentials or production Drive.
New comment creation on PDFs, Word files, Sheets, Slides or folders is rejected:
there is no supported native text-anchor implementation for those types in this
change. Existing threads on other file types retain read/reply/resolve support.

## Acceptance criteria

- AC-01: Every newly planned `add` requires a nonempty, unique exact `anchor` in
  the Google Doc body. Missing, repeated, out-of-tree, `_LitMan`, non-Docs,
  multi-tab and suggestion-touching targets fail before saving an actionable
  plan or writing. The preview shows comment content, quoted text, tab/range and
  context. Verify: new cases in `tests/dossier/test_comments.py`, tool schema tests
  and the real Docs discovery conformance tests.
- AC-02: Applying an accepted anchored plan uses native Docs requests with a
  required revision, rechecks tree membership and capabilities, keeps body text
  unchanged, and returns the actual comment ID. Stale revisions fail without
  retargeting. General Drive comment creation is never used, including from
  unfinished legacy plans. Verify: comment, adapter, assembly and legacy-plan
  regression tests, including a spy that rejects any Drive `create_comment` call.
- AC-03: An anchored comment is only reported as created after persistence and
  its anchor are confirmed. `ALL_FAILED_UNKNOWN_REASON`, missing/unknown save
  state, missing response IDs, lost replies and ambiguous reconciliation do not
  produce false success or a second blind insertion. Verify: comment fault
  injection tests covering each response and retry state described below.
- AC-04: `list_comments` returns native quoted text and current anchor metadata,
  supports the existing resolved filter, and provides routable IDs. New native
  threads can be replied to and resolved; existing general threads and threads
  on other file types remain accessible. No existing comment is deleted or
  migrated. Verify: `test_comments.py`, `test_files.py`, adapters and interface
  routing tests with mixed historical/native thread fixtures.
- AC-05: `set_text_style` can apply/change a `#RRGGBB` highlight and clear it,
  affecting exactly the accepted matches, without changing text or unrelated
  style properties. Invalid colors and fields are rejected. Verify:
  `test_documents.py`, tool validation and discovery request conformance tests.
- AC-06: `set_text_style` can add/change/remove an HTTP(S) URL on accepted text.
  The preview contains the complete URL or removal indication and Google's native
  formatting notice. Invalid URLs and partial overlap with a pre-existing link
  are rejected; link side effects cannot extend beyond accepted ranges. Verify:
  document tests with styled text and split text runs, and adapter/schema tests.
- AC-07: Both new style fields use the existing revision, Unicode, scope and
  suggestion guards. After an uncertain write, recovery recognizes an already
  applied result without writing; it never overwrites intervening format-only
  changes just because the body hash matches. Verify: document recovery tests
  for unchanged revision, changed text, changed highlight, changed URL, and an
  already applied result with a lost response.
- AC-08: CLI/MCP schemas, product help and instructions, architecture, operations,
  decisions and changelog describe the same supported behavior and recovery
  limits. Run the full Harness suite and Core regression suite with the required
  UV cache setting; keep the metadata adapter read-only. Verify: interface and
  agent-resource tests, both suite outputs, and documentation review.
- AC-09: In an expressly authorized disposable dossier, a person sees a comment
  attached to the intended phrase/title, reads/replies/resolves it through
  LitMan, applies/clears a highlight, and follows/changes/removes a hyperlink.
  Body text and document identity remain unchanged. Verify: recorded manual
  protocol with actual results, described under verification. This criterion is
  pending until that authorized test occurs; automated fixtures do not satisfy it.

## Approach

### Anchored comments only

Keep `preview_comment_changes` / `apply_comment_changes` and the operation names
`add`, `reply`, `resolve`. Change `add` to require exactly `op`, `content` and
`anchor`; `anchor` is a case-sensitive literal substring, within one paragraph,
1–1,000 characters, appearing exactly once. A section comment selects its title
text rather than assuming a page number or a mutable whole-section boundary.
No assistant-supplied numeric indexes, fuzzy matching, artificial anchor strings
or fallback general comments are accepted.

Reuse `DocumentText.matches`, context, UTF-16 indexing and pending-text-suggestion
checks through a small shared helper or a narrow public DocumentService method;
do not copy an alternate text parser into the comment service. Reuse the current
single-tab restriction; include the actual tab ID in native ranges. New anchored
creation requires `canComment`, editor access (`canEdit` and a usable revision),
and successful read of the selected text. Explain that commenter-only accounts
cannot use this guarded creation path; they retain access to legacy operations
where permissions allow. All newly planned native reply/resolve batches also
require editor access for their required-revision guard; existing raw-ID Drive
reply/resolve operations retain the existing `canComment` check. Recheck these
conditions on apply.

Validate native comment/reply content against the documented 2,048 UTF-8-unit
limit (encode to UTF-8 for the byte limit, not Python character length), including
accented characters and emoji. Legacy Drive replies keep their current limit.
Normalize native IDs into opaque public IDs `docs:<raw-id>` and leave historical
Drive IDs unchanged. Native reply/resolve requests remove only this prefix and
use `addCommentReply`, including `post.commentAction: RESOLVE` for resolution.
No assignment fields are exposed.

Add a dedicated `DocsGateway.get_with_comments` method rather than making every
document read ask for comment permissions. Fetch inline suggestions, document
comments and tab anchors, and normalize thread author, timestamps, replies,
resolved state, quoted text, current ranges and whether the anchor still exists.
Preserve the current list envelope and add `source` and `anchor` fields per
comment. A deleted/orphaned anchor is explicitly absent, never reconstructed
from a stale quote. Comments remain document content, not instructions.

For Google Docs, list native threads and historical Drive threads. If raw IDs
are identical, prefer the native representation; otherwise retain both source
identities without merging by equal content. Raw historical IDs continue to
route through Drive, while prefixed native IDs route through Docs. This avoids
assuming undocumented cross-API ID equivalence. Non-Docs listing and existing
thread operations remain on Drive. Do not hide a native read failure behind an
empty list or a silent Drive fallback. Validate this coexistence in AC-09.

Store a backend discriminator in every new comment plan. A plan may contain
1–10 native operations or 1–10 legacy Drive reply/resolve operations, never both
backends; mixed requests fail with an explanation to prepare separate plans.
The native operations are stored in one `PlanAction` of kind
`docs_comment_batch`, carrying the closed operation list, resolved request list,
backend and per-operation evidence in metadata and its revision in
`expected_version`. This one batch uses one accepted revision, so successive
comment creations do not invalidate each other's revision. Keep operation
indexes in metadata to distinguish identical requested comments. Body mutation
requests are prohibited in this batch.

### Persistence and recovery

Before sending a native batch, persist an attempt marker and the initial native
thread/reply IDs, expected selections and content. Save returned thread/reply IDs
and `commentUpdateState` before read-back when possible. For an ordinary response,
require `ALL_SAVED` plus read-back of returned IDs and the actual native anchor
for additions before completing the operation. Resolution is confirmed by thread
state; replies by their returned post IDs. Missing fields are not fabricated.

If the response explicitly reports failed saving, retain a recoverable error
`comment_save_failed`, perform read-back, and never mark the action complete
without evidence. Missing or unknown save state requires reconciliation, not an
assumption that HTTP 200 means success. Reconciliation may complete a result
only if all requested effects can be unambiguously observed.

On a lost response, compare against pre-send IDs and require the active author,
exact content, fresh timestamp and matching live anchor/quote for each addition;
exclude IDs already claimed by another operation. For replies match the parent
thread plus a new post; for resolution inspect current thread state. Multiple
candidates or unverifiable anchors are a conflict. Zero candidates after a sent
attempt is `comment_write_uncertain` and remains recoverable: retrying the same
plan only reconciles, it does not send again. Include
`write_may_have_occurred: true` in uncertainty error details and never represent
that state as a proven no-write result. A delayed or failed read is not
proof of absence. Report the operation ID and the uncertainty plainly; a person
must inspect it before deciding to prepare a fresh plan. A never-sent plan can
send once under its original revision. Use existing OperationRun notes/statuses;
no new global state machine or hidden comment marker is needed.

Check stored legacy plans before dispatch: any unfinished unanchored `add` is
rejected with `comment_anchor_required` and recovery instructions. Do not rewrite
an accepted plan or delete an already created comment. Completed legacy operations
can replay their recorded historical result; pending reply/resolve actions remain
supported. Reject a whole unfinished legacy plan containing an `add` before any
other remaining writes, so ordering cannot partially bypass the restriction.

### Highlighting and hyperlinks

Extend the existing `set_text_style` operation with optional fields:

```json
{"op":"set_text_style","find":"Pending team data","occurrences":1,"highlight_color":"#FFFF00"}
{"op":"set_text_style","find":"Pending team data","occurrences":1,"highlight_color":null}
{"op":"set_text_style","find":"Technical specifications","occurrences":1,"link_url":"https://example.org/specifications"}
{"op":"set_text_style","find":"Technical specifications","occurrences":1,"link_url":null}
```

Omitted fields mean unchanged; explicit null means remove. At least one of the
three existing flags or these two fields must be present. Permit flags, highlight
and link together in one operation on the same match, avoiding conflicting
overlapping operations. Keep existing occurrence-count and single-paragraph
rules. Canonicalize hex case; require six hexadecimal digits. Use the standard
JSON Schema representation `type: ["string", "null"]`. The current small
`_validate_value` supports neither union types nor `null`; add only those type
checks, retain array/item validation, and test existing type failures as well as
both new nullable fields. Validate again inside the service. Invalid types do
not reach Google.

Highlight uses `updateTextStyle` and a field mask containing `backgroundColor`
only (plus any other explicitly requested properties); convert hex channels to
RGB fractions. Null sets `backgroundColor` to an empty OptionalColor, representing
transparent rather than white. Do not clear other fields with a broad mask.

Link uses the `link` field mask and `link: {url: ...}`; null clears that field.
Accept only absolute HTTP(S) URLs with a host, no user-info or control characters,
maximum 2,048 characters. Do not fetch or validate the destination over the network.
Allow Drive document URLs without inferring or modifying their sharing permissions.
Google's normal link color/underline and removal behavior is accepted; display a
short notice in the preview and document it. This is not a promise to preserve
all visual styling when a link is removed.

Inspect full existing link runs before planning a change: if the requested range
cuts through a pre-existing link, reject with `partial_link_overlap` and ask for
the whole link text. For a link split across adjacent runs with the same target,
coalesce its contiguous extent first. Apply this check to set/change/removal.
Never expand the accepted range silently. Normalized style spans are derived
from the same raw Docs response and mapped to visible text offsets; retain hidden
text boundaries and suggested-style changes relevant to affected properties.
Reject relevant pending style/link suggestions rather than applying through them.

### Format recovery and read-back

Add narrow extraction of current style runs for affected ranges. Store requested
property preconditions and expected postconditions in new style-plan metadata;
include link extent/default side effects where relevant. No need to return every
font property in ordinary `read_google_doc` responses. The preview reports before
and requested after values of the new fields with the existing context.

New style plans retain the current unchanged-text hash and original required
revision. On resume after `sent`, first compare text and requested properties:
if the postcondition is present, complete without another write. If not, only
resend when the revision is still exactly the preview revision and preconditions
match. If it changed, return `document_changed`, including for format-only changes.
Never resend on a newer revision based only on body equality. Successful writes
with a read-back failure retain evidence and reconcile on retry. Preserve old
stored plan loading; do not invent style preconditions for old plans. For old
style-only plans without those fields, allow a resend only on the original
revision; otherwise conflict and require a new preview. Update the existing
recovery tests and rationale accordingly, without changing text-edit recovery.

### Alternatives and decisions

- Extend existing tools rather than add a parallel editing interface or arbitrary
  Google request execution. Reuse plans, scope checks, and deterministic matching.
- Native Docs comments supersede the decision that comment creation is unanchored
  in `harness/docs/decisions.md`. Preserve legacy thread access; no deletion or
  document reconstruction is part of this change.
- Retain one-tab mutation and literal anchors rather than add a heading parser,
  page-number targeting, multi-tab selection or an LLM-based locator.
- Use typed style fields rather than a separate highlighting tool or free-form
  color/request objects. Explicit null avoids a second set of remove operations.
- Replace text-hash-only style retries with evidence-based recovery because styles
  can change without text changes. Record this amendment in the existing decision.

## Implementation notes

### Code and tests

- `harness/src/litman_harness/adapters/docs.py`: add narrow comment reads, retain
  full batch responses, handle native save states in the owning service; distinguish
  a stale revision from invalid request ranges/unsupported comment requests. Do not
  map every new 400 to `document_changed`. Keep authentication and disabled-API
  errors intact and bound error details. No discovery or request bodies from agents.
- `adapters/metadata.py`: mirror the new gateway method with a read-only error;
  preserve the shared-state concurrency gate and no-write behavior.
- `dossier/documents.py`: share literal target resolution, extend style validation,
  extract style/link spans from raw Docs content, narrow masks, and add safe style
  postcondition recovery. Prefer small helpers in this module over a new framework.
- `dossier/comments.py`: inject Docs/DocumentService, anchored validation, native
  plan batch, reconciliation, ID routing and legacy-plan restriction. Add native
  normalization here and let FileService delegate; avoid two implementations of
  native comment interpretation.
- `dossier/files.py` and `interfaces/assembly.py`: wire the comment service once and
  route `list_comments` through the shared implementation without a dependency
  cycle. Keep the existing public file-service call signature.
- `interfaces/tools/{documents,files}.py` and, if needed, `interfaces/tools/__init__.py`:
  closed schemas, nullable fields, required anchor semantics, visible preview
  descriptions and no backend fields supplied by the assistant. Existing tool
  names remain shared between CLI and MCP.
- `tests/fakes.py`: native threads/anchors/replies/save-state responses and general
  JSON text styles, including link-run splitting and transparent highlight clearing.
  Fakes must exercise observable behavior, not merely record a constructed request.
- Extend `tests/dossier/test_{comments,documents,files}.py`,
  `tests/adapters/test_{docs,drive}_adapter.py`,
  `tests/interfaces/test_{tools,assembly,agent_files}.py` as affected.
  Use real packaged discovery schema tests alongside fakes to prevent request-shape
  assumptions. Explicitly cover accents/emoji, identical comments, orphaned anchors,
  format-only concurrent edits, missing responses, and unfinished old plans.

### Documentation and product guidance

Update `harness/docs/architecture.md`, `harness/docs/operations.md`,
`harness/docs/decisions.md`, and `CHANGELOG.md` under `Unreleased`. Update only
the authorized capability descriptions in
`harness/agent/skills/conectar-licitacion/SKILL.md`,
`harness/agent/skills/ayuda-litman/SKILL.md`, and
`harness/agent/workspace/AGENTS.md`: anchored-only new comments, section-title
selection, highlight/link add/change/remove, acceptance, normal link appearance,
native limits and uncertain-operation recovery. Keep repository-published prose
in English per AGENTS.md; do not edit unrelated product prompts or instructions.
No Core public contract/schema change is required.

### Verification protocol

Run both required package suites, from their respective directories:

```sh
UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q
```

Docker is not affected. Perform the manual AC-09 only after a person explicitly
authorizes a disposable dossier/document and real Google access. The design and
its approval alone do not authorize production credentials or resources.
Record actual account permission level, installed client version, success/failure
and observed UI results without secrets or customer content. Verify:

1. A unique section title and an accented/emoji-containing phrase can each receive
   a visible anchored comment, on the same existing document.
2. `list_comments` returns its quote/range and routable ID; reply and resolve work.
   One pre-existing general comment remains accessible. Inspect cross-API listings
   for duplicate views of the same native thread; do not assume ID equivalence.
3. Yellow highlight changes to another hex color, then becomes transparent, without
   modifying the text or neighboring formatting.
4. A phrase links to an explicit URL, then a second URL, then has no link. Google's
   normal styling is acceptable; neighboring links remain untouched.
5. Editing the document between preview and apply produces a conflict rather than
   moving a comment/highlight/link to a different phrase.

AC-09 is a required acceptance criterion of the second task. If authorization or
the live service is unavailable, record it as pending and do not claim acceptance
or close that task. No browser automation, alternate connector or direct API
script bypasses the product-agent LitMan-tools-only rule. Visual observation is
by the person using Google Docs, while LitMan performs authorized operations.

## Tasks

The tasks are ordered because they share the Docs adapter, fake, interface tests
and documentation. Integration is intentionally omitted to use repository
`git.integrate` unless the person supplies a preference before registration.

```yaml
- id: CHG-10.1
  title: Enforce anchored-only native comments with verified recovery and legacy access
  depends_on: []
  complexity: complex
  review: [quality, conformance]
  scope:
    - "harness/src/litman_harness/adapters/docs.py"
    - "harness/src/litman_harness/adapters/metadata.py"
    - "harness/src/litman_harness/dossier/comments.py"
    - "harness/src/litman_harness/dossier/documents.py"
    - "harness/src/litman_harness/dossier/files.py"
    - "harness/src/litman_harness/interfaces/assembly.py"
    - "harness/src/litman_harness/interfaces/tools/files.py"
    - "harness/tests/**"
    - "harness/docs/**"
    - "harness/agent/**"
    - "CHANGELOG.md"
  acceptance:
    AC-01: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_comments.py tests/interfaces/test_tools.py tests/adapters/test_docs_adapter.py'"
    AC-02: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_comments.py tests/interfaces/test_assembly.py tests/adapters/test_docs_adapter.py'"
    AC-03: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_comments.py tests/adapters/test_docs_adapter.py'"
    AC-04: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_comments.py tests/dossier/test_files.py tests/interfaces/test_tools.py'"
- id: CHG-10.2
  title: Add highlighting and hyperlinks and verify the complete document workflow
  depends_on: [CHG-10.1]
  complexity: complex
  review: [quality, conformance]
  scope:
    - "harness/src/litman_harness/dossier/documents.py"
    - "harness/src/litman_harness/adapters/docs.py"
    - "harness/src/litman_harness/interfaces/tools/documents.py"
    - "harness/src/litman_harness/interfaces/tools/__init__.py"
    - "harness/tests/**"
    - "harness/docs/**"
    - "harness/agent/**"
    - "CHANGELOG.md"
  acceptance:
    AC-05: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_documents.py tests/interfaces/test_tools.py tests/adapters/test_docs_adapter.py'"
    AC-06: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_documents.py tests/interfaces/test_tools.py tests/adapters/test_docs_adapter.py'"
    AC-07: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_documents.py tests/interfaces/test_assembly.py'"
    AC-08: "Run the required full Harness and Core suites from each package and review updated capability documentation and changelog."
    AC-09: manual
```

## Risks and open questions

- Actual native API support, visual anchor behavior and Drive/native thread
  coexistence have not been tested with the person's account. AC-09 is the gate;
  schema support and HTTP 200 alone are not acceptance evidence.
- All native comment mutations require editor access. Supporting native mutations
  for users with comment-only access would require a separate concurrency design
  and is excluded; historical Drive reply/resolve permission rules are preserved.
- Google supplies no caller-chosen idempotency key for comment insertion. After a
  sent request with no provable result, the safe outcome is explicit uncertainty,
  not automatic reinsertion. This can require human inspection.
- Existing general comments are preserved. New adds on non-Docs and pending
  unanchored plans intentionally stop working; document this compatibility change.
- Google's link creation/removal can alter visual style. That behavior is accepted
  by the person; partial existing links must still be refused to bound side effects.
- Integration preference was requested asynchronously. If no answer arrives, omit
  per-task `integrate` and inherit the repository configuration. No design approval
  or task implementation is inferred from permission to write this design.
