# Harness decisions

This log records durable package-level choices. Cross-package architecture and
development-process decisions belong in the repository
[decision log](../../docs/decisions/README.md). Current implementation detail
belongs in [architecture](architecture.md) or [operations](operations.md).

## Harness remains a separate process client of Core

Harness and Core are independent Python distributions. Harness invokes
`litman-core` and consumes only the repository-owned
[public CLI contract](../../docs/contracts.md); it does not import Core or
consume internal run files. This keeps deployment and internal evolution
independent while giving the process boundary an explicit compatibility policy.

## Drive access uses each employee's personal OAuth account

Harness opens a dossier by folder ID with the `drive` scope. It does not reuse
Core's service-account publisher, and secrets never cross CLI/MCP inputs or
dossier state. This preserves the person's Drive permissions and avoids a
second authorization model. The narrower `drive.file` scope was rejected
because it cannot open by ID a dossier created outside the app.

## Resource membership is established by ancestry

The membership adapter follows parent IDs within the connected Drive until it
reaches the dossier root. It never uses a global search. This makes every read
and write depend on structural membership rather than a name or a potentially
ambiguous query.

## Mutations use preview, explicit acceptance, and resumable local plans

Every business mutation is first represented by an account-bound local plan.
An apply call accepts the exact `plan_id`; created resources carry operation and
action markers. The result is a visible acceptance boundary plus deterministic
recovery after interruption, without storing private plans in the dossier.

## File changes are a closed, protected batch that trashes but never deletes

Folder and file organization is one previewed batch rather than separate open
ended operations. The closed set makes protection, capability and name-collision
checks deterministic, and marker adoption makes created resources resumable.
The root, `_LitMan`, manifest/context resources, and manifest-managed originals
or artifacts retain their stable roles. Drive deletion was rejected: `trash`
uses `files.update` with `trashed: true`, so it remains reversible.

## Drive v2 ETags guard shared state

An authorized 2026-10-15 smoke test established that Drive API v2 media updates
honor `If-Match` with strong ETags. Harness uses that capability for manifest
and context writes because Drive v3 does not expose the required ETag. Drive
`version` was rejected: harmless opening and server-side processing changed it
and caused false stale-plan results. Content SHA-256 protects manifest previews,
while original files use `md5Checksum` as their content identity.

## External context edits are preserved

`contexto.md` is derived from the manifest, but people may edit it. A mismatch
therefore completes the underlying business mutation while returning the
proposed deterministic content as `context_conflict`. Replacement requires a
new, explicit `overwrite_context: true` preview and still uses optimistic
concurrency.

## Provider choice is installation configuration

Harness validates and stores one Core provider and optional model through
`setup`, then snapshots the choice in each analysis plan. This avoids hidden
provider changes between preview and execution and leaves provider execution
inside Core.

## Originals are placed by capability, never deleted

Tender originals belong in the `Originales` folder, but a team member's
shared-drive role may allow copying without moving or deleting. Harness reads
`canMoveItemWithinDrive` and `canCopy` per file: it moves when allowed, copies
otherwise, and registers the file in place with a visible warning when neither
is possible. It never trashes the source, because the person may lack the right
and the file belongs to the team. Copying then trashing and always copying were
rejected: the first is destructive and often not permitted, and the second
duplicates files even when moving is allowed.

## Results are published flat in the phase folder

Analysis artifacts are uploaded straight into the registered `Analisis inicial`
or `Analisis detallado` folder, so the person finds the latest results where
they expect them. Core's artifact names are fixed, so a repeated analysis gets
a date suffix (`<stem> (YYYY-MM-DD)<ext>`, then `-2`, …) instead of a new
folder. Emptying the folder first was rejected because it deletes results the
manifest, summary and `contexto.md` still cite, and the person may lack the
right; uploading a new revision of the previous file was rejected because two
analyses would share one file ID and lose manifest traceability.

## Publication is part of analysis execution

An accepted analysis plan includes its publication actions. Harness validates
Core's public artifacts into a closed local catalog before any upload, then
publishes without asking for a second acceptance. Failed publication remains
recoverable and does not rerun Core or duplicate confirmed uploads.

## Procurement summaries require human acceptance and cited sources

Harness has no LLM. A chat assistant or constrained read-only reader proposes a
fixed-shape summary; a person accepts it. Each substantive value cites a
registered dossier resource, and Harness checks format and provenance rather
than claiming to verify meaning. This keeps generation outside the deterministic
runtime and acceptance explicit.

## Document edits use closed index-based operations guarded by the Docs revision

The assistant changes a dossier Google Doc only through closed operations
(`replace_text`, `insert_after`, `append`, and the style operations
`set_paragraph_style`, `set_text_style`, `set_list`) that the preview resolves
to Docs indexes on the text it read and simulates into an expected text. The apply
sends one `documents.batchUpdate` of index-based `deleteContentRange` and
`insertText` requests in descending index order, guarded by
`writeControl.requiredRevisionId`; a lost answer is resolved by comparing the
body with the expected text's hash. A plan holds text operations or style
operations, never both. A style-only plan leaves the text unchanged, so the hash
cannot prove that its batch was applied. It was first resent with the current
revision whenever the body text still equaled the planned text; that was
replaced (CHG-10) because a collaborator's format change leaves the text equal,
and resending would overwrite it. Now the plan stores the requested values and
their previous values per match: on resume a document showing every requested
value completes without a write, an unchanged preview revision allows one
resend on that revision, and anything else is a `document_changed` conflict
with `write_may_have_occurred: true`. Highlighting and links extend
`set_text_style` with nullable typed fields (`highlight_color`, `link_url`)
instead of a separate tool or free-form color and request objects; null
removes. A link change that cuts through an existing link is refused, because
Docs would change the whole link beyond the accepted text. `replaceAllText` was rejected because it
matches case-insensitively by default, reaches every tab, header, and footer,
and cannot be limited to the counted matches. Exporting to DOCX and re-uploading
was rejected because it destroys formatting, comments, revision history, and the
live-offer ID; free-form Docs requests from the assistant were rejected because
they have no deterministic preview; computer use in a browser was rejected as
unreliable and outside the acceptance model. Docs v1 uses the existing `drive`
scope, so no new login is required, but the Google Docs API must be enabled in
the OAuth client's Cloud project.

## The assistant is restricted to LitMan tools by instructions, not client configuration

The MCP server `instructions`, the workspace `AGENTS.md`, and
`conectar-licitacion` tell the assistant to use only LitMan tools for dossiers
and Drive files, never computer use, a browser, other Drive connectors, scripts,
or Google APIs directly, and to say that LitMan has no tool for a request and
suggest asking the developer when nothing fits. The rule leads the first 512
characters of the instructions because clients may show only that much. Tool
annotations derived from `Tool.mutates` and `Tool.destructive` let clients
prompt for approval by risk. Writing Computer Use or permission settings into
the person's global client configuration was rejected: Codex documents only an
administrator switch, and the change would be global and invasive. Instructions
are guidance, not enforcement, so real client behavior is checked manually.
A help skill with a test that covers the whole registry was preferred over a
`help` tool, so the answer stays in business language without growing the MCP
surface.

## `read_file` is a general reader beside `read_document`

`read_file` reads any file of the dossier tree (PDF, DOCX, text, XLSX, Google
Docs, Sheets and Slides) with the same paging and content note, instead of
widening `read_document`. `read_document` stays limited to registered originals
and published artifacts because the summary's provenance depends on that
restriction. Membership is proved with `belongs_to_root` and `in_litman`, as
for the Google Docs tools, and Excel files are read with `openpyxl` in
read-only mode so that a large workbook is never loaded whole.

## Google Sheets writes are closed, hash-guarded ranges with RAW values

The assistant changes a dossier Google Sheet only through closed operations
(`update_range`, `append_rows`) resolved to explicit A1 ranges; `append_rows`
resolves the first empty row so a lost answer never appends twice. Each range
is written with `values.update` and `valueInputOption: RAW`, so no formula or
external data ever reaches a sheet this way. Sheets v4 has no revision
control like Docs, so the apply re-reads each range and compares its SHA-256
against the preview's expected and current values instead: equal to the
expected values completes without writing (a lost answer), equal to the
preview's current values is written, and anything else is a `sheet_changed`
conflict. This leaves a narrow, documented race between an action's read and
its write, accepted because Sheets offers no optimistic-concurrency primitive
to close it. Sheets API v4 uses the existing `drive` scope, so no new login is
required, but the Google Sheets API must be enabled in the OAuth client's
Cloud project.

## Product agents are separate from development agents

Files under `harness/agent/` are installed product behavior. Repository skills
and instructions under `.agents/`, `.claude/skills/`, and `AGENTS.md` govern
development. Keeping these systems separate prevents Factory tooling from
silently changing the user's LitMan assistant, or vice versa.

## Comments are unanchored and resumed by author, content, and time

**Superseded (2026-10-21, CHG-10)** by "New comments are native, anchored
Google Docs comments" below; the resume rule still applies to replies to
historical Drive comments.

`preview_comment_changes`/`apply_comment_changes` add, reply to, or resolve
Drive comments without an anchor to a span of the document: Drive comment
anchors are not reliably rendered back in Google Docs, so an anchored comment
would be unverifiable from the harness side. Without a marker a resume could
search for, a lost answer is instead resolved by adopting an existing comment
or reply from the active account (`author.me`) with the same content and a
`createdTime` later than the newest one the preview saw on that file, rather
than creating a duplicate. Two identical comments written by the same person
after the preview remain genuinely ambiguous and are reported as a conflict,
not silently merged.

## New comments are native, anchored Google Docs comments

Since 2026-10-21 (CHG-10) every new comment is a native Google Docs comment
(`insertComment`) anchored to one exact, unique phrase of a single-tab Google
Doc, such as a section title; general comments are never created, and new
comments on other file types are refused. Drive custom anchors are not rendered
as text anchors by Workspace editors, while native Docs comments are, and they
can be read back with their live anchor. Native operations travel in one
`documents.batchUpdate` guarded by the preview revision, so they need editor
access; commenter-only access is out of scope because it would need a separate
concurrency design. Google offers no idempotency key for comment insertion, so
an operation is reported only after a read-back proves it; after a sent
attempt without proof the safe outcome is an explicit, recoverable uncertainty
(`comment_write_uncertain`, `write_may_have_occurred`), never an automatic
reinsertion. Historical Drive comments stay readable, replyable and resolvable
by raw ID, native threads are addressed as `docs:<id>`, and no cross-API ID
equivalence is assumed beyond showing an identical raw ID once. Existing
comments are neither deleted nor migrated, and an accepted plan with an
unfinished unanchored `add` is refused rather than rewritten.

## Dossier drift is detected on demand and repaired only by accepted plans

Since 2026-10-27 (CHG-12) `status` compares the manifest to Drive only when
called, reporting unregistered candidates, renamed or content-changed
registered resources, misplaced originals and artifacts, inaccessible or
out-of-tree references, and external `contexto.md` edits as a `drift` list;
it never writes, and a truncated walk is reported as incomplete rather than a
clean inventory. Repairs go through a separate, closed
`preview_reconciliation`/`apply_reconciliation` pair (retire or reactivate an
original, adopt its current name, rename a managed resource, place an
original, return a published artifact, or adopt a copy created during a prior
conflict), bound to the active account and the manifest content seen at
preview time, with the same `If-Match`, operation-marker and context-conflict
behaviour as every other mutation. No background watcher, scheduled job, or
silent manifest write exists. `litman-dossier-v2` adds only the active/retired
distinction for originals: v1 is read with every original active, and the
first accepted shared-state write migrates it to v2; older Harness versions
already read an unknown version read-only. A retired original keeps its ID and
provenance for history but is excluded from new analysis input and active
reference checks; reactivation requires the same ID and its stored MD5, so a
replacement file is registered as a new original instead. Dropping retired
originals was rejected because it would break summary and analysis
provenance; a silently ignored v1-only field was rejected because an older
client could then include a retired original in a new analysis without
knowing.

## Analysis selection rechecks a registered original's lifecycle and manifest MD5

`preview_analysis` treats a selected original differently depending on its
manifest status. An unregistered file may still be selected (always by
explicit ID, never inferred by name); a retired original is rejected with
`retired_original_requires_reactivation`, because reactivation is an explicit
decision with its own identity and checksum rule (see the retirement decision
above) that analysis must not bypass; an active registered original is
rechecked against the manifest's stored MD5 before the plan is built, and a
mismatch raises `registered_original_changed` instead of silently analyzing
content the person never reviewed. This is one targeted `load_state` read,
not a `status` candidate scan, keeping the check close to the cost of the
existing membership and capability checks it joins. Each planned action also
records whether its original was registered, so a human reading the plan can
see a new candidate was included. Analysis preview additionally runs the same
candidate scan `status` runs for unregistered originals, once, to report
other eligible files the person did not select
(`other_candidate_original_ids`) without adding them to the plan: selection by
ID stays the only way a file enters an analysis, but a person reviewing the
preview can see what else is available. A truncated scan is reported as such
rather than implying completeness. The same two checks (retirement, MD5) run
again immediately before Core runs, against the manifest's state at that
moment rather than the one seen at preview: an accepted plan can sit
unexecuted, and the manifest can change in that window (most plainly, the
same original being retired through an accepted reconciliation plan). A
preview-only check would let that plan still run Core on a retired or
changed original, silently reintroducing the exact risk the guard exists to
close.
