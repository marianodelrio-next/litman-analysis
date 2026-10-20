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
(`replace_text`, `insert_after`, `append`) that the preview resolves to Docs
indexes on the text it read and simulates into an expected text. The apply
sends one `documents.batchUpdate` of index-based `deleteContentRange` and
`insertText` requests in descending index order, guarded by
`writeControl.requiredRevisionId`; a lost answer is resolved by comparing the
body with the expected text's hash. `replaceAllText` was rejected because it
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
