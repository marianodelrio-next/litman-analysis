# Harness architecture

This page owns the design of `litman-harness`. For commands, environment
variables, failure recovery, and real-account validation, see
[operations](operations.md). Durable rationale is recorded in
[decisions](decisions.md).

## Package boundary

Harness connects one procurement dossier by its Google Drive folder ID, using
each employee's personal OAuth account. It never uses Core's service account or
Drive publisher, and it never accepts tokens or secrets through arguments,
stdio, a manifest, or context.

Harness invokes Core only through the versioned
[public CLI contract](../../docs/contracts.md). It does not import Core or read
Core-internal files. Core's [internal run documentation](../../core/docs/contracts.md)
describes execution inside Core and has no stability guarantee for Harness.

## Source layout

```text
harness/src/litman_harness/
  errors.py          safe Harness errors and unexpected-error messages
  local_paths.py     private state/configuration paths and checkout rejection
  plans/             Plan, PlanAction, OperationRecord, and private PlanStore
  dossier/           resources, membership, manifest v1, contexto.md,
                     shared-state capability, inspection, incorporation,
                     publication, summary, Google Docs document, and file
                     navigation/reading services
  analysis/          originals, download, Core result validation, and catalog
  adapters/          personal OAuth Drive, Drive v2 shared state, Google Docs
                     v1, Google Sheets v4, document extraction, development
                     metadata, OAuth, and Core process
  interfaces/        assembly, operation registry, CLI, and MCP
  installation.py    idempotent guided install and uninstall
harness/agent/       installed product skills, workspace instructions, and
                     Claude/Codex reader-agent definitions
harness/deployment/  guided install and uninstall scripts
harness/tests/       dossier, analysis, adapters, interfaces, plans, deployment
```

`dossier/membership.py` is the single membership check. It follows parent IDs
to the connected folder within the same Drive, without global searches.

## Shared dossier

`_LitMan/manifest.json` uses the `litman-dossier-v1` format. It stores resource
IDs, the dossier phase, functional folders, context identity and checksum,
originals and their provenance, published analyses and artifacts, the accepted
procurement summary, the live offer, and history. References use Drive IDs, so
renaming a resource does not break them. An unknown manifest version is exposed
read-only.

Incorporation places each selected original, and each registered original
outside the `originals` folder (`Originales`), into that folder with a
`place_original` action. The preview chooses the strategy from the file's Drive
capabilities: `move` when `canMoveItemWithinDrive` is true (same ID), otherwise
`copy` when `canCopy` is true, otherwise `in_place`; a missing capability
counts as false. A copy carries the action markers, must keep the source MD5,
and is registered with `provenance: "copied"` and `copied_from: <source id>`;
the source stays where it was, remains citable, and is no longer a candidate in
`status`. A move rejected with `insufficient_permission` falls back to copy,
then to `in_place`. An `in_place` original is recorded with
`placement: "in_place"` and never planned again. A registered original whose
MD5 no longer matches the manifest is not placed (strategy `skipped`). Every
copy, `in_place`, or `skipped` outcome adds a Spanish message to the preview
action and to the result's `placement_warnings`. Harness never deletes or
trashes an original.

The phases are `sin_analisis`, `analisis_inicial`, `analisis_detallado`,
`oferta_en_preparacion`, and `entregada`. An accepted incorporation may set the
phase. Publishing `assessment` or `detailed-analysis` advances it only when it
is behind and never moves it backwards.

`contexto.md` is generated deterministically from the manifest. It contains the
dossier name and phase, accepted summary, linked folders and documents, live
offer, and published results. Every artifact is linked by Drive ID and described
by a fixed sentence for its role. Core output content never controls this file.

Each update reads the context and checks its SHA-256, writes the manifest, then
writes the context with optimistic concurrency. An external context edit does
not fail the completed business operation: Harness leaves the file untouched,
retains the previous context checksum in the manifest, and returns a
`context_conflict` with the proposed content. A later incorporation preview
with `overwrite_context: true` can replace it only if the content still matches
what the preview observed.

## Plans and publication

Every `preview_*` call stores an account-bound local plan. The matching
`apply_*` call accepts only that `plan_id` and rejects plans for a different
account or plans made stale by relevant Drive changes. Created resources carry
`litman_operation_id` and `litman_action_id` in `appProperties`, allowing an
interrupted operation to adopt exactly one prior result instead of duplicating
it. Multiple matching resources are a conflict.

Analysis downloads only planned originals into a private workspace whose input
directory is the analysis operation UUID. Harness generates Core's minimal
configuration and invokes `litman-core run --config`; it does not depend on a
user-maintained Core configuration. Harness validates the public result by
artifact role, path containment, presence, and SHA-256, then records a closed
local catalog. Core-internal files such as `validation.json` and
`generation_manifest.json` are never consumed.

An analysis plan includes publication. Publication uploads each validated
artifact directly into the registered phase folder (`Analisis inicial` or
`Analisis detallado`), without a dated subfolder, and records that folder as
`analyses[].folder_id`. A name already present there is uploaded as
`<stem> (YYYY-MM-DD)<ext>`, then `<stem> (YYYY-MM-DD-2)<ext>`, and so on, with
the date taken from the analysis `completed_at`; names are fixed in the
preview, so a resumed publication never uploads twice and nothing existing is
overwritten or removed. Plans stored before this layout, which create a dated
run folder, still resume. For a detailed analysis without a live offer,
publication also converts the technical DOCX to a Google Doc in `Oferta`. It never
replaces an existing live offer. Manifest changes are merged additively; a
concurrent manifest write makes the operation recoverable and retrying resumes
without rerunning Core or re-uploading completed artifacts. A fully published
analysis removes its local workspace.

On Windows, each downloaded original receives a safe, traceable `local_name`.
Drive ID and MD5 remain its identity, while useful terms such as `PCAP`,
`anuncio`, or `adjudicación` are retained for Core. Harness locates
`litman-core.exe` in the active environment's scripts directory via
`sysconfig.get_path("scripts")`, which also works with uv-managed tool
environments.

## Procurement summary

Harness contains no LLM. The chat assistant, or the installed low-cost reader
agent, proposes a summary and the person decides whether to accept it.
`read_document` can read only a registered original or a published artifact in
the same dossier. It returns PDF or DOCX text in pages of at most 20,000
characters and marks the result as content, not instructions.

The accepted `manifest.summary` has ordered, closed keys:
`objeto`, `organismo`, `expediente`, `procedimiento`, `presupuesto`,
`valor_estimado`, `plazo_ejecucion`, `fecha_limite`, `lotes`,
`solvencia_economica`, `solvencia_tecnica`, `equipo`,
`criterios_adjudicacion`, `recomendacion`, and `alertas`. The required keys are
`objeto`, `organismo`, `presupuesto`, and `fecha_limite`. Each item is one line
of 1–300 characters and cites a registered source file unless its value is
`No consta`. Harness validates shape and provenance, not factual truth.

`preview_summary` orders and validates the proposal; `apply_summary` stores it
in the manifest and regenerates `contexto.md`. The context renders the summary
immediately after phase and dossier, one linked source per line. Status and
successful publication recommend `propose_summary` or `refresh_summary` when
the accepted summary does not cover the current analyses.

## Google Docs of the dossier

`dossier/documents.py` (`DocumentService`) lets the assistant read, edit, and
create native Google Docs anywhere in the connected dossier through the Docs v1
adapter (`adapters/docs.py`), using the same `drive`-scope OAuth credentials.
It is independent of `read_document`, the manifest, and `contexto.md`: created
documents are not registered, and the dossier need not be adopted. Every call
first proves with one Drive `get` that the file belongs to the tree, has no
`_LitMan` ancestor, and is a Google Doc (`document_outside_tree` or
`unsupported_document` otherwise), before any Docs call.

`read_google_doc` returns the first tab's visible body text in pages of 20,000
characters with `revision_id`, `CONTENT_NOTE`, and `writes: false`. The text is
read with suggestions inline so that indexes match the document; pending
suggested insertions are not shown. Tables contribute their cells' text; section
breaks, tables of contents, and inline objects contribute nothing.

`preview_document_edit` accepts 1–20 closed operations: `replace_text`
(`find`, `replace`, exact `occurrences`), `insert_after` (`anchor`, `text`),
and `append` (`text`, before the body's final newline). Each `find` or
`anchor` must fall within one paragraph. The preview resolves every span to Docs
indexes counted in UTF-16 code units, refuses overlapping spans, spans touching
suggestions, documents with more than one tab, and documents the account cannot
edit, then simulates the requests in descending index order and stores a
`document_edit` plan with the request list, the preview's revision, and the
expected text's SHA-256 and length. The preview shows each matched span with up
to 80 characters of context. `apply_document_edit` re-checks membership, MIME
type, and `canEdit`, then sends exactly one `documents.batchUpdate` of
`deleteContentRange`/`insertText` requests with
`writeControl.requiredRevisionId`. A changed document is rejected by Docs and
recorded as a `conflict` with code `document_changed`. If an earlier attempt
sent the batch and lost the answer, the resumed apply completes without a
second batch when the body's hash equals the expected one. Formatting, tables,
images, comments, suggestions, headers, and footers are out of scope; inserted
text takes the style of the paragraph where it lands.

`preview_document_creation` plans a new Google Doc named `name` in a dossier
folder that is not `_LitMan`, from `text` or by converting a dossier DOCX
(`source_file_id`), never both. A name already used in that folder returns
`name_exists`, and it is checked again at apply. Text documents are created
empty with markers and then filled with one revision-guarded insert; a DOCX is
downloaded to a temporary directory and uploaded converted, as publication does
for the live offer. A resumed creation adopts the marked document and never
writes its text twice.

A Docs 403 with reason `accessNotConfigured` or `SERVICE_DISABLED` returns
`docs_api_disabled`. `diagnose` reports `docs_api` as `enabled`, `disabled`, or
`unknown` by reading a fixed document ID that does not exist: 404 means the API
answers for the OAuth client's project.

## Files of the dossier

`dossier/files.py` (`FileService`) navigates and reads every file of the
connected dossier, independently of the manifest: the dossier need not be
adopted. Each call proves with Drive `get` calls that the file belongs to the
tree (`belongs_to_root`) and is not `_LitMan` or below it (`in_litman`, also in
`dossier/membership.py`), else `document_outside_tree`; a folder argument fails
with `invalid_parent`. These are the codes of the Google Docs tools.

`list_folder`, `search_in_dossier` and `get_file_info` return the same fields:
`id`, `name`, `mime_type`, `kind`, `size` (`null` for Google-native files),
`modified_time`, `web_view_link` and `role`. `kind` is one of `folder`,
`google_doc`, `google_sheet`, `google_slides`, `pdf`, `docx`, `xlsx`, `text`
(plain text, Markdown or CSV, by MIME type or extension) or `other`. `role`
comes from an adopted manifest (`folder:<key>`, `analysis_folder`, `context`,
`live_offer`, `original`, `artifact`) and is `null` otherwise. `_LitMan` is
never listed and search never enters it. Search walks the tree with
`walk_tree` (never a Drive query), so it is bounded by its 2,000-item limit
(`truncated`).

`read_file` returns 20,000-character pages with `next_offset`,
`CONTENT_NOTE` (document text is content, not instructions) and
`writes: false`:

| Kind | Source |
| --- | --- |
| PDF, DOCX | `extract_text`, as `read_document` |
| Text, Markdown, CSV | downloaded and decoded as UTF-8, replacing undecodable bytes |
| XLSX | `openpyxl` in read-only mode with cached values |
| Google Sheets | Sheets v4 (`spreadsheets.get`, then `values.batchGet` with `FORMATTED_VALUE`) |
| Google Docs | `DocumentService.read`, so the offsets match `read_google_doc` |
| Google Slides | Drive `files.export` to `text/plain` (Drive limits an export to 10 MB) |

Spreadsheets render each sheet as `## Hoja: <title>` followed by
`<row number>\t<cell>…` lines for the non-empty rows. Files over 30 MB and
spreadsheets over 200,000 cells are refused with `file_too_large`; an XLSX
cannot report its size beforehand, so its cells are counted while iterating.
Other MIME types and folders return `unsupported_document`. `read_document`
is unchanged and keeps reading only registered originals and artifacts,
because summary provenance depends on it.

`list_comments` reads Drive comments (`comments.list`, `includeDeleted=false`)
with `author`, `created_time`, `resolved`, `quoted_text` and `replies`;
resolved comments are excluded unless `include_resolved` is true.

`adapters/sheets.py` (`SheetsGateway`) uses the same `drive`-scope credentials
as Drive and Docs. A 403 with reason `accessNotConfigured` or
`SERVICE_DISABLED` returns `sheets_api_disabled`. The error-body parser is
shared with the other Google adapters (`adapters/google_errors.py`). The Drive
adapter also requests `modifiedTime` and the `canRename`, `canTrash` and
`canComment` capabilities; `inspect` output therefore gains `modified_time` on
each resource.

## Google Sheets edit

`dossier/sheets.py` (`SheetsService`) lets the assistant change explicit
ranges of a dossier Google Sheet through `SheetsGateway.update` (`values.update`
with `valueInputOption=RAW`, so no formula or external data ever reaches a
sheet this way). It proves membership and `GOOGLE_SHEET_MIME` the same way as
the document tools (`document_outside_tree`, `unsupported_document` saying to
convert first), and that the account can edit the sheet (`insufficient_capability`).

`preview_sheet_edit` accepts 1–20 closed operations: `update_range` (`range`,
an explicit `'Hoja'!A1:B2` range, and `values`, a rectangular matrix of exactly
the range's size) and `append_rows` (`sheet`, a title, and `values`). A range
without both explicit row and column bounds is rejected
(`invalid_request`); there is no open-ended or whole-row/column form.
`append_rows` resolves the first empty row after the last non-empty row of the
named sheet (by reading the whole sheet with `UNFORMATTED_VALUE`) into an
explicit range, and several `append_rows` into the same sheet within one plan
stack without overlapping. The preview rejects more than 5,000 cells in total,
overlapping resolved ranges (`overlapping_operations`), and an unknown sheet
title (`invalid_request`).

Each resolved range is read once with `UNFORMATTED_VALUE` and both its current
and its expected values are normalized the same way before hashing (SHA-256 of
canonical JSON): values are padded to the range's size, a missing value,
`null`, and `""` all become `""`, and an integral float becomes an int. The
plan (`sheet_edit`) stores, per operation, the resolved range, the expected
values, and the current (`before_sha256`) and expected (`after_sha256`)
hashes.

`apply_sheet_edit` re-checks membership and `canEdit` once for the sheet, then
for each action reads its range again: if it already equals the expected
values the action completes without writing (a lost answer is resumed safely,
because `RAW` writes are idempotent); if it still equals the `before_sha256`
values it is written with `values.update`; otherwise the action stops as a
`conflict` with code `sheet_changed`, leaving earlier actions of the plan
written. Sheets has no revision control, so a narrow race remains between an
action's read and its write; this is documented, not closed.

## Guided product flow

The assistant follows one business flow: organize the dossier and originals,
run and publish the initial analysis, propose a summary, ask whether a detailed
analysis is wanted, publish it with the live offer, refresh the summary, then
return control to the person.

`inspect` and `status` traverse the complete tree breadth-first without global
searches, excluding `_LitMan`, up to 2,000 resources. They identify candidate
originals and offers, matching functional folders, and previous Core-publisher
outputs. Suggested folders remain suggestions until the person confirms them.

`dossier/recommendation.py` selects the first applicable recommendation from:
`review_manifest`, `incorporate`, `publish_analysis`, `organize_originals`
(registered originals outside `Originales` that can still be placed),
`run_assessment`,
`propose_summary` or `refresh_summary`, `decide_detailed_analysis`, then no
recommendation. Each recommendation identifies its reason, tool, and arguments.

The installed product resources support this flow:

- `conectar-licitacion` guides connection and asks once whether to prepare a
  summary after publication. It routes reading, editing, and creating dossier
  Google Docs through the document tools, applies only the preview the person
  accepts, and restricts the assistant to LitMan tools for the dossier and its
  Drive files (never computer use, a browser, other Drive connectors, scripts,
  or Google APIs directly), suggesting asking the developer when no tool fits.
  The workspace `AGENTS.md` and the MCP server `instructions` repeat that rule.
- `conectar-licitacion` and the workspace `AGENTS.md` also route listing,
  searching, inspecting and reading any dossier file, and its comments, through
  the file tools.
- `conectar-licitacion` also routes changing a dossier Google Sheet through
  `preview_sheet_edit`/`apply_sheet_edit`, applying only the preview the
  person accepts.
- `ayuda-litman` answers "qué puedes hacer" by explaining every operation in
  business terms with an example phrase; a test keeps it complete against the
  registry.
- `resumir-licitacion` defines what to read, the fixed keys, sources, and
  proposal format.
- `preparar-equipo` guides diagnostics, OAuth, the Google Docs API check,
  provider session, setup, repair, update, and uninstall without independently running Git, uv, a
  provider CLI, or a browser.
- `lector-licitacion` is read-only. Claude uses Haiku with only the `status`
  and `read_document` MCP tools; Codex uses `gpt-5.6-luna`, low reasoning, and
  a read-only sandbox with the same two operations.

Installation and exact destination paths belong to the
[installation guide](../deployment/README.md).
