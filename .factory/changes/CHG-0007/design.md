# CHG-0007 — LitMan-only assistant guidance, a help skill, and more dossier file tools

## Context
Verified on `master` at `0f8cab6`, with CHG-0006 complete (all three tasks merged):

- **What happened:** in a real test with the Codex app on Windows, the assistant tried to work on
  Drive through computer use. Nothing in the product resources says that LitMan tools are the only
  allowed route, and nothing tells the assistant what to do when no tool covers a request.
- **MCP server:** `harness/src/litman_harness/interfaces/mcp.py`.
  - `_initialize` returns only `protocolVersion`, `capabilities` and `serverInfo`, with no
    `instructions`.
  - `tools/list` returns `Tool.descriptor()` (`interfaces/tools/__init__.py`), which carries only
    `name`, `description` and `inputSchema`; there are no MCP tool annotations.
  - `Tool` already has `mutates: bool`.
- **What clients read:**
  - Codex reads the MCP `instructions` field as server-wide guidance and recommends that its first
    512 characters stand on their own
    (https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
  - In Codex, Computer Use is a plugin. The only documented hard switch is the administrator setting
    `[features].computer_use = false` in `requirements.toml`; a user has no simple switch
    (https://learn.chatgpt.com/docs/computer-use.md). The person decided that instructions are
    enough.
- **Product resources:** they live under `harness/agent/`:
  - `workspace/AGENTS.md` is installed to `~/LitMan/AGENTS.md`, with `CLAUDE.md` pointing to it.
  - Skills: `conectar-licitacion`, `resumir-licitacion`, `preparar-equipo`.
  - Subagent: `lector-licitacion`.
  
  `installation.py` installs the skills listed in `SKILL_NAMES`. `tests/interfaces/test_agent_files.py`
  checks that tools referenced by skills exist in `registry()`. CHG-0006-03 added a
  document-specific "never computer use or the browser" rule to `conectar-licitacion` (step 8) and
  `workspace/AGENTS.md`. `interfaces/assembly.py` `docs_api_status()` probes the Docs API for
  `diagnose` (`docs_api`).
- **Current tools:** `interfaces/tools/{dossier,documents,analysis,setup}.py`.
  - CHG-0006 added `read_google_doc`, `preview_document_edit`/`apply_document_edit` (closed text
    operations `replace_text`, `insert_after`, `append`) and
    `preview_document_creation`/`apply_document_creation` (from `text` or by converting a dossier
    DOCX `source_file_id`). These live in `dossier/documents.py` (`DocumentService`, `DocumentText`,
    `planned_edits`, `simulated_text`, `OPERATIONS`).
  - `read_document` (`dossier/summary.py`) reads only registered PDF/DOCX originals and artifacts.
    It stays unchanged, because summary provenance depends on it.
- **Drive adapter:** `adapters/drive.py` (`DriveGateway`, `GoogleDriveGateway`).
  - `_FIELDS` and `_CAPABILITIES` request `canListChildren`, `canAddChildren`, `canDownload`,
    `canEdit`, `canMoveItemWithinDrive` and `canCopy`. They do not request `canRename`, `canTrash`,
    `canComment` or `modifiedTime`.
  - `http_error(status)` maps by status only.
  - `adapters/docs.py` already parses Google error reasons (`_reasons`) and maps
    `docs_api_disabled`.
  - `adapters/metadata.py` mirrors each gateway as read-only.
- **Dossier helpers:**
  - `dossier/tree.py`: `walk_tree` (breadth-first, at most 2,000 items, never into `_LitMan`),
    `_normalized` and `LITMAN_FOLDER`.
  - `dossier/membership.py`: `belongs_to_root`.
  - `dossier/service.py`: `ExpedienteService.root()`, `apply_plan()`, `ensure_marked()`,
    `OperationRun.note/complete/output`, `OperationConflict`, `action_id()`.
  - `dossier/manifest.py`: `Manifest.references()` and `summary_sources()`.
  - `DocumentService._below_litman()` (`dossier/documents.py`) checks the `_LitMan` ancestry.
- **Dependencies:** `harness/pyproject.toml` has `pypdf`, `python-docx` and
  `google-api-python-client`. The last one ships the Docs, Drive and Sheets discovery documents.
  The person authorized adding `openpyxl` to read Excel files.
- **Drive export:** Drive `files.export` is limited to 10 MB. Google Docs export to PDF, DOCX,
  Markdown and TXT; Sheets to PDF, XLSX and CSV (first sheet only); Slides to PDF and PPTX
  (https://developers.google.com/workspace/drive/api/guides/ref-export-formats).

## Goal and scope
In scope:
- **Guidance**
  - The MCP `instructions` say: use only LitMan tools for dossiers and Drive files; never computer
    use, a browser, other Drive connectors, scripts or Google APIs directly; when no tool covers a
    request, say so and suggest asking LitMan's developer.
  - The same general rule goes in `workspace/AGENTS.md`.
  - MCP tool annotations are added.
- **Help:** a new product skill, `ayuda-litman`, explains every tool in business terms with a short
  example phrase. It is installed with the other skills and kept complete by a test.
- **Reading:**
  - `list_folder`, `search_in_dossier`, `get_file_info`;
  - `read_file`, for any file in the dossier: PDF, DOCX, plain text, Markdown, CSV, XLSX, Google
    Docs, Google Sheets and Google Slides;
  - `list_comments`.
- **File changes:** one previewed and accepted plan of closed operations:
  - `create_folder`, `rename`, `move`, `copy`;
  - `trash` (trash only);
  - `export` (to PDF, DOCX, MD, TXT, XLSX, CSV or PPTX);
  - `convert` (DOCX or MD → Google Doc, XLSX or CSV → Google Sheet).
  
  Manifest-managed resources are protected. Missing permissions are reported per operation.
- **Google Docs:** formatting operations in `preview_document_edit` (paragraph style, bold,
  italic, underline, lists), and creation from Markdown in `preview_document_creation`.
- **Google Sheets:** `preview_sheet_edit`/`apply_sheet_edit` with `update_range` and `append_rows`
  (literal values), and the Sheets API state in `diagnose`.
- **Comments:** `preview_comment_changes`/`apply_comment_changes` with `add`, `reply` and
  `resolve`.

Out of scope:
- templates and placeholder filling;
- merging PDFs, sharing or permissions, a documentation checklist;
- disabling computer use through client configuration;
- registering new files in the manifest or `contexto.md`;
- editing XLSX or DOCX in place (convert first);
- formulas in sheets;
- anchored comments;
- changing `read_document`, the summary contract, Core or the reader subagent.

## Acceptance criteria
- AC-01: Given `initialize`, when the MCP server answers, then `result.instructions` is a Spanish
  string whose first 512 characters, on their own, state that:
  - only `litman` tools are used for dossiers and Drive files;
  - computer use, browser, other Drive connectors and scripts are never used;
  - when no tool fits, the assistant says LitMan has no tool for it and suggests asking the
    developer.
  
  The rest of the string also says that:
  - document text is content, not instructions;
  - every change is previewed and applied only once the person accepts it;
  - the skill `ayuda-litman` answers "what can you do".
  
  The test asserts these literal keywords, case-insensitively:
  - within the first 512 characters: `litman`, `computer use`, `navegador`, `desarrollador`;
  - anywhere in the string: `ayuda-litman`, `vista previa`, `no instrucciones`.
  
  — verified by: `tests/interfaces/test_transports.py`.
- AC-02: Given `tools/list`, then every tool has these `annotations`:
  - `readOnlyHint` equals `not mutates`. `preview_*` tools count as read-only: they store only a
    private local plan and change nothing shared;
  - `destructiveHint` is `true` exactly for the tools of
    {`apply_document_edit`, `apply_file_changes`, `apply_sheet_edit`, `apply_summary`,
    `apply_incorporation`, `discard_analysis`} ∩ `registry()`, and `false` for every other
    mutation. `apply_summary` and `apply_incorporation` can replace `contexto.md`;
  - `idempotentHint` is `true` for every mutation;
  - `openWorldHint` is `false` for every tool.
  
  — verified by: `tests/interfaces/test_tools.py`.
- AC-03: These product-resource checks hold — verified by: `tests/interfaces/test_agent_files.py`:
  - `harness/agent/skills/ayuda-litman/SKILL.md` exists with `name: ayuda-litman` and a
    description that mentions "qué puedes hacer".
  - It contains every name in `registry()` as `` `name` ``, each with an example line
    (`Ejemplo:`).
  - `workspace/AGENTS.md` and `conectar-licitacion/SKILL.md` contain the general LitMan-only rule
    (they mention computer use and the developer fallback) and refer to `ayuda-litman`.
  - From CHG-0007-04 on, `conectar-licitacion` no longer says that formatting is out of reach; from
    CHG-0007-06 on, it no longer says that comments are.
- AC-04: Given `litman install` for Claude or Codex, then `ayuda-litman` is installed next to the
  other skills, recorded in the install manifest, and removed by `uninstall` — verified by:
  `tests/test_installation.py`.
- AC-05: Navigation tools — verified by: tests in `tests/dossier/test_files.py`:
  - **`list_folder(folder_id, parent_folder_id?)`** returns, for the root or a folder in the tree
    and never `_LitMan` or below it:
    - each child's `id`, `name`, `mime_type`, `kind`, `size`, `modified_time` and
      `web_view_link`;
    - `kind`, one of `folder`, `google_doc`, `google_sheet`, `google_slides`, `pdf`, `docx`,
      `xlsx`, `text` (plain text, Markdown, CSV) or `other`;
    - `size`, which is `null` for Google-native files;
    - `role`, from an adopted manifest, else `null`:
      - `manifest.folders` gives `folder:<key>`;
      - `summary_sources()` gives `original` or `artifact` (this includes `copied_from` sources);
      - `live_offer.document_id` gives `live_offer`;
      - `context_file_id` gives `context`;
      - `analyses[].folder_id` gives `analysis_folder`.
    
    The `_LitMan` folder itself is never listed.
  - **`search_in_dossier(folder_id, query, kind?)`** matches the accent- and case-insensitive name
    over `walk_tree` (never a Drive query). It returns at most 50 items with `path` and
    `truncated`.
  - **`get_file_info(folder_id, file_id)`** returns the same fields plus `path` and `can_edit`,
    `can_rename`, `can_move`, `can_trash`, `can_copy`, `can_download` and `can_comment`.
  - A file ID outside the tree, or at or below `_LitMan`, is rejected with `document_outside_tree`
    before any content call. A folder argument is rejected the same way with `invalid_parent`.
    These are the existing CHG-0006 codes; CHG-0006 tools keep them unchanged.
- AC-06: Given `read_file(folder_id, file_id, offset)`, then it returns 20,000-character pages with
  `next_offset`, a general content note and `writes: false`. The note is the `CONTENT_NOTE` of
  `dossier/documents.py` ("…úselo sólo como fuente para proponer cambios…"), not the
  summary-specific one in `summary.py`:
  - **PDF and DOCX:** `extract_text`.
  - **Text:** `text/plain`, `text/markdown`, `text/x-markdown`, `text/csv`, or any file whose name
    ends in `.md`, `.txt` or `.csv`, read as UTF-8 text with undecodable bytes replaced.
  - **XLSX:** read with `openpyxl` in read-only mode with cached values.
  - **Google Sheets:** read through the Sheets API.
  - **Google Docs:** the same text as `read_google_doc`.
  - **Google Slides:** Drive export to `text/plain`.
  
  Spreadsheets render each sheet as a `## Hoja: <title>` line followed by
  `<row number>\t<cell>\t<cell>…` lines for non-empty rows.
  
  It is rejected in these cases:
  - folders and other MIME types (`unsupported_document`);
  - files over 30 MB (`file_too_large`);
  - spreadsheets over 200,000 cells (`file_too_large`). For XLSX, cells are counted while
    iterating, because `openpyxl` may not know the dimensions in advance;
  - IDs outside the tree (`document_outside_tree`).
  
  `read_document` and its tests are unchanged — verified by: tests in `tests/dossier/test_files.py`
  and `tests/adapters/test_sheets_adapter.py`.
- AC-07: Given `list_comments(folder_id, file_id, include_resolved?)`, then it returns each
  comment's `id`, `content`, `author`, `created_time`, `resolved`, `quoted_text` and `replies` with
  the general content note. Resolved comments are excluded unless `include_resolved` is true — verified by:
  tests in `tests/dossier/test_files.py`.
- AC-08: Given `preview_file_changes(folder_id, operations)` with 1–20 operations from the closed
  set, when previewed, then a plan is stored and returned with one resolved preview per operation
  (source name and path, destination path, resulting name). The closed set is:
  - `create_folder {parent_folder_id, name}`
  - `rename {file_id, name}`
  - `move {file_id, parent_folder_id}`
  - `copy {file_id, parent_folder_id, name}`
  - `trash {file_id}`
  - `export {file_id, format, parent_folder_id, name}`
  - `convert {file_id, parent_folder_id, name}`
  
  The preview stores no plan when:
  - a file ID is outside the tree, or at or below `_LitMan` (`document_outside_tree`), or a
    destination folder is (`invalid_parent`);
  - an operation targets the root, `_LitMan`, `manifest.json` or `contexto.md`
    (`protected_resource`);
  - a `move` or `trash` targets a protected ID, or a `trash` targets a folder with any protected ID
    below it (`protected_resource`). Protected IDs are:
    - every `Manifest.references()` ID;
    - every `summary_sources()` key (registered originals, their `copied_from` sources and
      published artifacts);
    - the manifest and context files;
  - a `move` targets the item itself or one of its descendants (`invalid_move`);
  - a name is empty, longer than 200 characters or has control characters (`invalid_request`);
  - a name already exists in the destination, including names produced earlier in the same plan
    (`name_exists`);
  - a file appears in more than one operation (`invalid_request`);
  - the format is not offered for the source MIME, the source cannot be converted, or a `copy`
    targets a folder (`unsupported_conversion`);
  - any required Drive capability is missing. Then one `insufficient_capability` error lists every
    blocked operation with its index and capability, so that the assistant can explain them all and
    preview again without them.
  
  — verified by: tests in `tests/dossier/test_file_changes.py`.
- AC-09: Given an accepted file-changes plan, when `apply_file_changes` runs, then each action is
  handled in this order:
  1. **Target state already reached** (renamed, moved, trashed, or a marked resource exists): the
     action completes, after adopting that resource.
  2. **Membership is re-checked.** For `trash`, the item's own `trashed` flag is ignored.
  3. **Protection, capabilities and `name_exists` are re-checked.** `name_exists` ignores the
     action's own source item and any resource that carries this action's markers.
  
  In addition:
  - **Created resources** (folders, copies, exports, conversions) carry markers, and on resume they
    are adopted with `ensure_marked`.
  - **Rename, move and trash** are completed without a call when the item is already in the target
    state.
  - **Trash** uses `files.update` with `trashed: true`; `files.delete` is never called.
  - **Final errors become conflicts:** `insufficient_permission` (a Drive 403 that is neither a rate
    limit nor an export-size error), `insufficient_capability`, `protected_resource`, `name_exists`
    and `export_too_large` (403 `exportSizeLimitExceeded`) raised during an action are raised as
    `OperationConflict`. The result is `status: "conflict"` with `{code, operation, completed}`.
    Earlier actions remain done. A new preview is needed for the operations that did not run.
  - **Rate limits:** a 403 `userRateLimitExceeded` or `rateLimitExceeded` returns the recoverable
    `drive_rate_limited`; repeating the acceptance resumes.
  - **Replay:** repeating a succeeded plan returns `replayed: true`.
  
  — verified by: tests in `tests/dossier/test_file_changes.py` and an offline Drive v3 discovery
  test in `tests/adapters/test_drive_adapter.py` for `files.update` (rename, trash), `files.export`
  and the generalized conversion upload.
- AC-10: Given `preview_document_edit` with the new closed style operations, then:
  - The operations are:
    - `set_paragraph_style {anchor, style}`, where `style` is `NORMAL_TEXT`, `TITLE`, `SUBTITLE`,
      `HEADING_1`, `HEADING_2` or `HEADING_3`;
    - `set_text_style {find, occurrences, bold?, italic?, underline?}`, with at least one flag;
    - `set_list {anchor, list}`, where `list` is `bullets`, `numbered` or `none`.
  - The requests are index-based `updateParagraphStyle`, `updateTextStyle`,
    `createParagraphBullets` and `deleteParagraphBullets` requests on the matched spans.
  - Style operations cannot be mixed with text operations in one plan (`mixed_operations`).
  - `set_list` refuses a paragraph that starts with a tab (`unsupported_document`).
  - The apply sends one guarded `batchUpdate`. A style-only plan whose answer was lost is resent on
    resume with the current revision only if the body text still equals the planned text;
    otherwise the result is a `document_changed` conflict.
  
  — verified by: tests in `tests/dossier/test_documents.py` and the offline Docs discovery test in
  `tests/adapters/test_docs_adapter.py`.
- AC-11: Given `preview_document_creation` with `markdown` (1–100,000 characters, exclusive with
  `text` and `source_file_id`), when applied, then a Google Doc is created in the parent by
  uploading the Markdown with conversion to `application/vnd.google-apps.document`, with markers.
  Repeating the acceptance after an interruption leaves one document — verified by: tests in
  `tests/dossier/test_documents.py` and the offline Drive discovery test.
- AC-12: Given `preview_sheet_edit(folder_id, spreadsheet_id, operations)` with 1–20 operations, a
  Google Sheet in the tree (else `document_outside_tree`) and `canEdit`, then a plan is stored with,
  for each operation, the target A1 range and the SHA-256 of its current and expected values. The
  operations are:
  - `update_range {range, values}`: `values` is a rectangular array of string, number, boolean or
    `null`, with exactly the range's size. `null` means an empty cell and is sent as `""`;
  - `append_rows {sheet, values}`: the preview resolves the first empty row after the last
    non-empty row into an explicit range.
  
  The preview rejects:
  - more than 5,000 cells (`invalid_request`);
  - overlapping ranges (`overlapping_operations`);
  - an unknown sheet (`invalid_request`);
  - a non-Sheets file (`unsupported_document`, saying to convert first).
  
  Values are read with `UNFORMATTED_VALUE` and hashed after normalization:
  - pad to the range's size;
  - missing values, `null` and `""` all become `""`;
  - integral floats become ints;
  - canonical JSON.
  
  Each apply action re-checks membership and `canEdit`, then reads its range:
  - equal to the expected values → completed without writing (lost answer);
  - equal to the preview values → written with `values.update` and `valueInputOption: RAW`;
  - anything else → `sheet_changed` conflict.
  
  — verified by: tests in `tests/dossier/test_sheets.py` and the offline Sheets v4 discovery test
  in `tests/adapters/test_sheets_adapter.py`.
- AC-13: Given a Sheets API 403 with reason `accessNotConfigured` or `SERVICE_DISABLED`, then the
  error is `sheets_api_disabled` with a Spanish message for the administrator. `diagnose` reports
  `sheets_api` as `enabled`, `disabled` or `unknown`, and never fails because of it — verified by:
  `tests/adapters/test_sheets_adapter.py` and `tests/interfaces`.
- AC-14: Given `preview_comment_changes(folder_id, file_id, operations)` with 1–10 operations, then
  a plan is stored. The operations are:
  - `add {content}`;
  - `reply {comment_id, content}`;
  - `resolve {comment_id, content?}`.
  
  `content` has 1–4,096 characters. The preview rejects:
  - IDs outside the tree (`document_outside_tree`);
  - unknown or deleted comment IDs (`comment_not_found`);
  - files without `canComment` (`insufficient_capability`).
  
  Apply re-checks membership and `canComment`.
  
  Apply:
  - creates an unanchored comment, a reply, or a reply with `action: "resolve"`;
  - on resume, adopts an existing comment or reply by the same author (`author.me`) with the same
    content and a `createdTime` later than the newest `createdTime` that the preview saw on that
    file, instead of creating a second one. Server time is used, never the local clock;
  - completes `resolve` without a call when the comment is already resolved.
  
  — verified by: tests in `tests/dossier/test_comments.py` and an offline Drive discovery test for
  `comments.create`, `comments.list` and `replies.create`.
- AC-15: Each task updates the documentation it affects — verified by: manual conformance review:
  - `harness/docs/architecture.md`, `operations.md` (operations table) and `decisions.md`;
  - `harness/deployment/README.md` (skills list, enabling the Sheets API);
  - `docs/guia-litman-windows.md` (Spanish, user-facing: ask "qué puedes hacer");
  - `docs/windows-codex-validation.md`, with manual real-account steps. These include checking how
    Codex and Claude prompt for approval of `preview_*` and `apply_*` tools once annotations exist,
    and that the assistant uses no computer use.
- AC-16: The full Harness suite passes — verified by:
  `bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'`.

## Approach
- **Guidance by instructions, not client configuration.**
  - The MCP `instructions` reach every client that supports them (Codex reads them), and
    `workspace/AGENTS.md` covers the session context. Both carry the same LitMan-only rule.
  - The developer fallback is a sentence in those instructions, not a new tool.
  - Writing Computer Use or permission settings into the person's global client configuration was
    rejected: there is no simple user-level switch, the change would be global and invasive, and
    the person chose instructions only.
- **Annotations derived from `Tool`.** Add `destructive: bool = False` to `Tool` and build
  `annotations` in `descriptor()` from `mutates` and `destructive`. Clients that ignore annotations
  are unaffected.
- **Help as a skill, kept complete by a test.** The person asks in natural language, so a skill with
  a matching description is the natural trigger. A test fails whenever a tool is added without a
  help entry. A `help` tool was rejected because the skill text can be in business language without
  growing the MCP surface.
- **One general reader instead of widening `read_document`.** `read_document` stays limited to
  summary sources, because summary provenance depends on it. `read_file` reads any dossier file
  with the same paging and content note.
- **One closed batch for file changes.** A single `preview_file_changes`/`apply_file_changes` pair
  follows the closed-operation model of `preview_document_edit`. It gives one acceptance for a set
  of organizing actions and one place for protections and capability checks, instead of seven tool
  pairs.
  - Operations cannot reference resources created in the same plan; a new folder needs its own
    plan first. This keeps every action independent and resumable.
- **Trash only.** Deleting is reversible (Drive trash). The Harness rule "never delete or trash an
  original" is preserved by protecting manifest references.
- **Name collisions return `name_exists`,** as document creation does. The assistant proposes
  another name; no automatic suffix is added.
- **Styles as separate plans.** Formatting does not change the text, so mixing it with text edits
  would require index remapping. Style-only plans keep the existing text model, simulation and
  revision guard. Re-sending style requests is idempotent, which makes lost-answer recovery safe.
- **Markdown creation through Drive conversion:** upload `text/markdown` converted to a Google Doc.
  This gives headings, lists, tables and emphasis without a Markdown-to-Docs-requests translator.
- **Sheets writes:**
  - `valueInputOption: RAW`, so no formulas and nothing that fetches external data.
  - Optimistic checks by value hash. Sheets has no revision write control, so a narrow race remains
    between the read and the write of an action; it is documented.
  - `append_rows` resolves to an explicit range, so a lost answer never appends twice.
- **Comments are unanchored.** Drive API anchors are not reliably rendered in Google Docs.
  Comments cannot carry markers, so resume adopts by author, content and creation time.
- **Decisions to add to `harness/docs/decisions.md`:**
  - "The assistant is restricted to LitMan tools by instructions, not client configuration".
  - "File changes are a closed, protected batch that trashes but never deletes".

## Implementation notes
**Shared conventions for every task:**
- Tools go in `interfaces/tools/`; register each new module in `registry()`. Spanish descriptions
  state "Consulta (no escribe)" or "Mutación"; mutations include the `_GATE` text when they write to
  Drive.
- Nested operation shapes are validated in the service, as in `validated_operations` in
  `dossier/documents.py`, because `validate_arguments` checks only top-level types.
- Every new tool gets an entry with `Ejemplo:` in `harness/agent/skills/ayuda-litman/SKILL.md`; the
  AC-03 test enforces it from CHG-0007-02 on.
- **Gateway methods:** each new method goes on the Protocol in `adapters/*.py`, the Google
  implementation, the read-only metadata gateway (`adapters/metadata.py`, same read-only error as
  existing writes) and the fakes in `tests/fakes.py`.
- **Offline discovery tests** follow `tests/adapters/test_drive_adapter.py`
  (`static_discovery=True`, `HttpMockSequence`).
- **Spanish texts:** product resources and user messages are in Spanish; developer docs are in
  English.

**CHG-0007-01 (guidance, annotations, help skill).**
- `mcp.py`: add a module constant `SERVER_INSTRUCTIONS` and return it as `instructions` in
  `_initialize`. Lead with the LitMan-only rule and the developer fallback in the first 512
  characters.
- `interfaces/tools/__init__.py`: add `Tool.destructive` and `annotations` in `descriptor()`. Mark
  `destructive=True` on `apply_document_edit` and `discard_analysis` now. Later tasks mark
  `apply_file_changes` and `apply_sheet_edit`; the AC-02 test lists the exact set and grows with
  them.
- **New `harness/agent/skills/ayuda-litman/SKILL.md`.**
  - Frontmatter: `name`, plus a `description` that triggers on "qué puedes hacer", "ayuda" and
    "qué herramientas tienes".
  - Body: tools grouped by business purpose (preparar el equipo, conectar y organizar la
    licitación, análisis, resumen, leer, documentos, archivos, hojas de cálculo, comentarios), each
    with one functional line and one `Ejemplo:` phrase.
  - End with the rule: if something is not on the list, say that LitMan cannot do it yet and
    suggest asking the developer.
  - This task covers the tools present at its start (including CHG-0006's); each later task adds its
    own.
- Add `ayuda-litman` to `SKILL_NAMES` in `installation.py`; update `tests/test_installation.py`.
- **Product resources:** in the existing short Spanish tone:
  - replace the document-only "never computer use or the browser" lines from CHG-0006-03 with the
    general LitMan-only rule, including the developer fallback, in `workspace/AGENTS.md` (the
    Google Docs bullet) and `conectar-licitacion/SKILL.md` (step 8);
  - keep the tool guidance of those lines;
  - add the `ayuda-litman` pointer;
  - update the CHG-0006-03 assertions in `test_agent_files.py` to match.
- Extend `test_agent_files.py` with the AC-03 checks.

**CHG-0007-02 (reading).**
- **Drive fields:**
  - add `canRename`, `canTrash` and `canComment` to `_CAPABILITIES`, and `modifiedTime` to
    `_FIELDS`;
  - add `modified_time: str | None = None` as the **last** field of `Resource`
    (`dossier/models.py`), and pass it in `Resource.from_api`, which builds positionally;
  - `Resource.json()` uses `asdict`, so `inspect` output gains `modified_time`, which is accepted.
- **New `dossier/files.py`, `FileService(dossier, docs_service, sheets)`.**
  - Move `_below_litman` from `DocumentService` into `dossier/membership.py` as
    `in_litman(drive, root, item)`, which also returns true when the item itself is named
    `_LitMan`. `DocumentService` uses it, keeping its error codes.
  - A helper `_resolve_in_tree(root, file_id)` combines `belongs_to_root` with `in_litman`.
  - `list_folder` and `search_in_dossier` filter out the `_LitMan` item that `walk_tree` and
    `children` return.
  - `role` comes from `Manifest.references()` plus published artifact IDs, when the dossier is
    adopted. It is `null` otherwise.
  - `search_in_dossier` uses `walk_tree` and `tree._normalized` (make it public as
    `normalized_name`).
- **`read_file`:**
  - Google Docs: delegate to `DocumentService.read` and return its text, so the offsets match
    `read_google_doc`.
  - XLSX: `openpyxl.load_workbook(path, read_only=True, data_only=True)`.
  - Google Sheets: `spreadsheets.get` (sheet titles and `gridProperties`, to enforce the cell cap
    before reading values) and then `values.batchGet` with `FORMATTED_VALUE` for display. Sheet
    edits in CHG-0007-05 read with `UNFORMATTED_VALUE`; the gateway takes the render option as a
    parameter.
  - Slides: a new `DriveGateway.export(file_id, mime_type, destination)` with Drive v3
    `files.export_media`.
  - Size: check `Resource.size` before downloading.
- **New `adapters/sheets.py`.**
  - `SheetsGateway` with `get(spreadsheet_id)` and `values(spreadsheet_id, ranges)`.
  - `sheets_http_error` mirrors `docs_http_error`: `sheets_api_disabled` for the disabled reasons,
    and 401/403/404 like Docs. Reuse `_reasons`, moved to a small shared helper module under
    `adapters/`.
  - `DesktopOAuthProvider.sheets_service()` mirrors `docs_service()` with `build("sheets", "v4",
    …)`.
  - Wire `sheets` and `files` into `Services` in `interfaces/assembly.py`; the metadata adapter gets
    a read-only Sheets gateway.
- **Comments:** `DriveGateway.comments(file_id)` calls `comments.list` with
  `includeDeleted=false`, paged, with fields `id`, `content`, `author(displayName,me)`,
  `createdTime`, `resolved`, `quotedFileContent(value)` and `replies(id,content,author,createdTime,
  action,deleted)`.
- **Dependency:** add `openpyxl>=3.1` to `harness/pyproject.toml` and refresh `harness/uv.lock`.
- **Tools:** add `interfaces/tools/files.py` with `list_folder`, `search_in_dossier`,
  `get_file_info`, `read_file` and `list_comments`.

**CHG-0007-03 (file changes).**
- **New `dossier/file_changes.py`, plan kind `"file_changes"`,** with one `PlanAction` per
  operation:
  - kinds: `create_folder`, `rename`, `move`, `copy`, `trash`, `export`, `convert`;
  - `resource_id` is the source and `parent_id` the destination;
  - `metadata` holds `name`, `format`, the target MIME and the operation index.
- **Required capabilities:**

  | Operation | Capabilities |
  | --- | --- |
  | `rename` | `canRename` |
  | `move` | `canMoveItemWithinDrive` on the item, `canAddChildren` on the destination |
  | `copy` | `canCopy`, `canAddChildren` |
  | `trash` | `canTrash` |
  | `export`, `convert` | `canDownload`, `canAddChildren` |
  | `create_folder` | `canAddChildren` |

  A missing capability counts as false.
- **Formats:**
  - **Export map:** Google Doc → `pdf`, `docx`, `md`, `txt`; Google Sheet → `pdf`, `xlsx`, `csv`;
    Google Slides → `pdf`, `pptx`.
  - **Convert map:** DOCX or `text/markdown` → Google Doc; XLSX or `text/csv` → Google Sheet.
- **New gateway methods:**
  - `rename(file_id, name)` and `trash(file_id)` with `files.update`;
  - `export` from CHG-0007-02;
  - generalize `upload_converted` with a `target_mime_type` parameter. Default it to the Google Doc
    MIME, so publication keeps working unchanged.
- **Exports:** export to a `tempfile.TemporaryDirectory()`, then `upload` with markers.
- **Error mapping:**
  - extend `http_error(status, content=None)` in `adapters/drive.py` with the shared `_reasons`
    parser:
    - `exportSizeLimitExceeded` gives `export_too_large`;
    - `userRateLimitExceeded`/`rateLimitExceeded` give `drive_rate_limited`;
    - other 403s give `insufficient_permission`, as today.
    
    `_execute` passes `exc.content`. `adapters/drive_state.py` keeps calling `http_error(status)`
    unchanged.
  - `apply_plan` (`dossier/service.py`) records only `OperationConflict` (and `concurrent_change`)
    as a conflict, and any other `HarnessError` as `RECOVERABLE`. The runner therefore wraps the
    final codes listed in AC-09 into
    `OperationConflict(details={"code": …, "operation": index, "completed": [...]})`.
- **Protected IDs:**
  - always: the root, `_LitMan` and anything below it, `manifest.json`, `contexto.md`;
  - for `move` and `trash` as well: `Manifest.references()` ∪ `summary_sources()` keys;
  - for `trash` of a folder: `walk_tree` from that folder must contain no protected ID.
  
  `rename` is refused only for the always-protected items.
- **Tools:** add `preview_file_changes` and `apply_file_changes` (`mutates=True`,
  `destructive=True`). Update `ayuda-litman`, `conectar-licitacion` (explain permission errors to
  the person; never retry by another route) and the docs.

**CHG-0007-04 (document formatting and Markdown creation).**
- **`dossier/documents.py`:**
  - extend `OPERATIONS` and `validated_operations` with the three style operations;
  - add a `STYLE_OPERATIONS` set and reject plans that mix both kinds;
  - `planned_edits` emits style requests for style operations with `fields` limited to the given
    properties;
  - for a style-only plan, `expected_sha256` is the current text hash.
- **`_run_edit` on resume:** when the action was sent, the text equals the expected text and the
  plan is style-only, resend with the current `revisionId`. A text plan keeps its current
  behaviour.
- **Creation:** `preview_creation` accepts `markdown`. The apply writes it to a temporary `.md` file
  and calls `upload_converted(..., source_mime_type="text/markdown")`. Update the creation tool
  schema and description.
- **FakeDocs** must store paragraph style, text style and bullet state, enough to assert the
  results.
- **Product text and decisions:**
  - In `conectar-licitacion/SKILL.md` step 7, rewrite "Formato, tablas, imágenes y comentarios
    quedan fuera: díselo a la persona." so that formatting is no longer excluded. Assert this in
    `test_agent_files.py`.
  - Amend the decision "Document edits use closed index-based operations guarded by the Docs
    revision" in `harness/docs/decisions.md` to cover style-only plans and their resend-on-resume
    rule.

**CHG-0007-05 (Sheets edit).**
- **New `dossier/sheets.py`, plan kind `"sheet_edit"`,** with one `PlanAction("write_range", …)`
  per operation.
  - `metadata`: range, values, `before_sha256`, `after_sha256`.
  - The hashes are computed over the normalized 2-D values: pad to the range's size with `""`;
    `null` becomes `""`.
- **Ranges:** parse and build A1 ranges with a small local helper (sheet title quoted with `'`,
  column letters and row numbers). Do not accept open-ended ranges.
- **`SheetsGateway.update(spreadsheet_id, range, values)`** calls `values.update` with
  `valueInputOption=RAW`.
- **`diagnose`:** add `sheets_api` with a `sheets_api_status()` that mirrors `docs_api_status()` in
  `interfaces/assembly.py`.
- **Tools:** add `preview_sheet_edit` and `apply_sheet_edit` (`destructive=True`).

**CHG-0007-06 (comments).**
- **New `dossier/comments.py`, plan kind `"comment_changes"`.**
  - The preview stores `created_after` in each action's metadata: the newest `createdTime` among
    the file's comments and replies, as listed by Drive, or `null` when there are none.
  - Gateway methods: `create_comment(file_id, content)` and
    `create_reply(file_id, comment_id, content, action=None)`, with fields that include
    `author(me)`.
- **Resume:** list the comments or replies and adopt exactly one match (`author.me`, equal content,
  `createdTime >= created_after`). More than one match is a `conflict`.
- **Tools:** add `preview_comment_changes` and `apply_comment_changes`.
- **Product text:** remove comments from the "quedan fuera" sentence of `conectar-licitacion`
  step 7, and assert this in `test_agent_files.py`.

## Tasks
Dependencies follow the code each task reuses:
- CHG-0007-01 first, because it creates the help skill and its coverage test.
- After it, CHG-0007-02 and CHG-0007-04 can run in parallel.
- CHG-0007-02 adds the shared pieces (`in_litman`, the new Drive capabilities, the shared `_reasons`
  helper, the Sheets adapter, comment listing, `DriveGateway.export`). After it, CHG-0007-03,
  CHG-0007-05 and CHG-0007-06 can run in parallel.

```yaml
- id: CHG-0007-01
  title: LitMan-only MCP instructions, tool annotations and the ayuda-litman help skill
  depends_on: [CHG-0006-03]
  complexity: normal
  review: [quality, conformance]
  scope: ["harness/src/litman_harness/interfaces/**", "harness/src/litman_harness/installation.py", "harness/agent/**", "harness/tests/**", "harness/docs/**", "harness/deployment/README.md", "docs/guia-litman-windows.md", "docs/windows-codex-validation.md"]
  acceptance:
    AC-01: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/interfaces/test_transports.py'"
    AC-02: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/interfaces/test_tools.py'"
    AC-03: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/interfaces/test_agent_files.py'"
    AC-04: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/test_installation.py'"
    AC-15: manual
    AC-16: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'"
- id: CHG-0007-02
  title: Dossier navigation, general file reading (Excel, Sheets, Slides, text) and comment listing
  depends_on: [CHG-0007-01]
  complexity: complex
  review: [quality, conformance]
  scope: ["harness/src/litman_harness/**", "harness/tests/**", "harness/agent/**", "harness/pyproject.toml", "harness/uv.lock", "harness/docs/**", "harness/deployment/README.md", "docs/guia-litman-windows.md", "docs/windows-codex-validation.md"]
  acceptance:
    AC-03: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/interfaces/test_agent_files.py'"
    AC-05: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_files.py'"
    AC-06: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_files.py tests/adapters/test_sheets_adapter.py tests/dossier/test_summary.py'"
    AC-07: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_files.py'"
    AC-15: manual
    AC-16: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'"
- id: CHG-0007-03
  title: Previewed file changes (folders, rename, move, copy, trash, export, convert) with protections and permission reporting
  depends_on: [CHG-0007-02]
  complexity: complex
  review: [quality, conformance]
  scope: ["harness/src/litman_harness/**", "harness/tests/**", "harness/agent/**", "harness/docs/**", "docs/guia-litman-windows.md", "docs/windows-codex-validation.md"]
  acceptance:
    AC-02: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/interfaces/test_tools.py'"
    AC-03: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/interfaces/test_agent_files.py'"
    AC-08: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_file_changes.py'"
    AC-09: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_file_changes.py tests/adapters/test_drive_adapter.py tests/dossier/test_publication.py'"
    AC-15: manual
    AC-16: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'"
- id: CHG-0007-04
  title: Google Docs formatting operations and document creation from Markdown
  depends_on: [CHG-0007-01]
  complexity: normal
  review: [quality, conformance]
  scope: ["harness/src/litman_harness/**", "harness/tests/**", "harness/agent/**", "harness/docs/**", "docs/guia-litman-windows.md", "docs/windows-codex-validation.md"]
  acceptance:
    AC-03: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/interfaces/test_agent_files.py'"
    AC-10: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_documents.py tests/adapters/test_docs_adapter.py'"
    AC-11: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_documents.py tests/adapters/test_drive_adapter.py'"
    AC-15: manual
    AC-16: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'"
- id: CHG-0007-05
  title: Previewed Google Sheets edits (update range, append rows) and Sheets API diagnosis
  depends_on: [CHG-0007-02]
  complexity: normal
  review: [quality, conformance]
  scope: ["harness/src/litman_harness/**", "harness/tests/**", "harness/agent/**", "harness/docs/**", "harness/deployment/README.md", "docs/guia-litman-windows.md", "docs/windows-codex-validation.md"]
  acceptance:
    AC-02: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/interfaces/test_tools.py'"
    AC-03: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/interfaces/test_agent_files.py'"
    AC-12: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_sheets.py tests/adapters/test_sheets_adapter.py'"
    AC-13: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/adapters/test_sheets_adapter.py tests/interfaces'"
    AC-15: manual
    AC-16: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'"
- id: CHG-0007-06
  title: Previewed comment changes (add, reply, resolve) with duplicate-free resume
  depends_on: [CHG-0007-02]
  complexity: normal
  review: [quality, conformance]
  scope: ["harness/src/litman_harness/**", "harness/tests/**", "harness/agent/**", "harness/docs/**", "docs/guia-litman-windows.md", "docs/windows-codex-validation.md"]
  acceptance:
    AC-03: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/interfaces/test_agent_files.py'"
    AC-14: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_comments.py tests/adapters/test_drive_adapter.py'"
    AC-15: manual
    AC-16: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'"
```

## Risks and open questions
- **Instructions are guidance, not enforcement.** A client could still offer computer use. Real
  Codex Windows behaviour must be checked manually (AC-15 step in
  `docs/windows-codex-validation.md`).
- **To confirm on a real account:**
  - Drive accepts `text/markdown` uploads converted to a Google Doc;
  - the Sheets API accepts the existing `drive`-scope token;
  - the exact error reasons for a too-large export and a disabled Sheets API.
  
  If Markdown import were rejected, AC-11 would need a fallback (plain-text creation) decided then.
- **The administrator must enable the Sheets API** in the OAuth client's Cloud project; until then
  the Sheets tools return `sheets_api_disabled`.
- **Sheets race:** a write can still race with a human edit between the read and the write of one
  action. The window is small, and the race is documented.
- **Comment resume:** two identical comments written by the same person after the preview would be
  ambiguous and end as a conflict.
- **Parallel tasks share files:**
  - `interfaces/tools/__init__.py` (`registry()`), `tests/fakes.py`, `ayuda-litman/SKILL.md` and
    the docs;
  - CHG-0007-04 and CHG-0007-06 both edit the "quedan fuera" sentence of `conectar-licitacion`.
  
  The task merged second rebases and resolves these textual conflicts. A task must not remove
  another task's help entries or `destructive` flags.
- **Existing installations** must run `litman install` again (the update phrase) to get
  `ayuda-litman`.
