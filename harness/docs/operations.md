# Harness operations and recovery

This page owns Harness configuration, interface behavior, concurrency,
recovery, and authorized real-account validation. See
[architecture](architecture.md) for component responsibilities and
[installation](../deployment/README.md) for end-user setup.

## Local configuration and OAuth

Harness rejects private paths inside the repository checkout. The following
environment variables override its defaults:

| Variable | Purpose | Default |
| --- | --- | --- |
| `LITMAN_HARNESS_METADATA` | Read-only, non-secret development metadata JSON | unset, so OAuth is used |
| `LITMAN_HARNESS_OAUTH_CLIENT` | Desktop OAuth client used by `login` | `$XDG_CONFIG_HOME/litman-harness/client_secret.json` |
| `LITMAN_HARNESS_OAUTH_TOKEN` | Personal token | `$XDG_CONFIG_HOME/litman-harness/token.json` |
| `LITMAN_HARNESS_PLAN_STORE` | Local plans and operation records | `$XDG_STATE_HOME/litman-harness/plans` |
| `LITMAN_HARNESS_WORK_DIR` | Analysis workspaces | `$XDG_STATE_HOME/litman-harness/work` |

Without `XDG_*`, POSIX uses `~/.config` and `~/.local/state`. Windows uses
`%LOCALAPPDATA%/litman-harness` for configuration and state. Explicit
`LITMAN_HARNESS_*` and `XDG_*` values take precedence. POSIX directories and
files use modes 0700 and 0600 respectively. Windows files inherit the user
profile ACL; `chmod` is not presented as a privacy guarantee there.

The interactive, CLI-only `litman login` runs the installed-app local-server
flow with the single `drive` scope. `drive.file` is insufficient because it
cannot open folders created outside the app by ID. A token with the wrong scope
returns `oauth_scope_missing`. An expired token with a refresh token is
refreshed and persisted; a missing or unrefreshable token returns
`oauth_login_required`.

The Google Docs tools use the same token with Docs API v1. The API must be
enabled once in the Google Cloud project that owns the OAuth client; until then
every Docs call returns `docs_api_disabled` and `diagnose` reports
`docs_api: "disabled"`. `unknown` means the check could not run (no usable
token, the metadata adapter, or another error); `diagnose` never fails because
of it.

The Google Sheets tools (reading and `preview_sheet_edit`/`apply_sheet_edit`)
use the same token with Sheets API v4, checked the same way: a disabled API
returns `sheets_api_disabled` and `diagnose` reports `sheets_api: "disabled"`;
`unknown` means the check could not run.

## Operations

CLI and MCP return the same envelope: `{"ok": true, "result": ...}` or
`{"ok": false, "error": {"code", "message", "details"}}`. Input is validated
against each operation's `inputSchema`, including required fields, types,
enums, and rejection of extra properties; invalid input returns
`invalid_request`.

| Operation | Kind | Responsibility |
| --- | --- | --- |
| `identity` | query | Report the active account. |
| `diagnose` | query | Report adapters, identity, scopes, Core contract/environment/provider, shared-state mechanism, Google Docs and Sheets API state (`docs_api`, `sheets_api`), guided-install state, and whether configured paths exist, never tokens or paths. |
| `inspect` | query | Inventory the connected folder tree, candidates, suggestions, and next actions. |
| `status` | query | Combine inspection with manifest status, read-only drift diagnostics, pending local publications, and `recommended_action`. |
| `preview_incorporation` | query | Plan only missing folders, originals, live offer, context, and manifest work. |
| `apply_incorporation` | mutation | Apply the accepted incorporation `plan_id`. |
| `preview_reconciliation` | query | Plan up to 20 closed repair actions (retire/reactivate an original, adopt its current name, rename a managed resource, place an original, return an artifact, adopt an already-created copy). |
| `apply_reconciliation` | mutation | Apply the accepted reconciliation `plan_id`; rechecks IDs, names, MD5, membership, permissions, manifest content, and context ETag. |
| `preview_analysis` | query | Plan Core analysis and publication with the provider fixed by `setup`; a selected original rejects `registered_original_changed` if a registered original's content drifted, or `retired_original_requires_reactivation` if it was retired, and the result lists other eligible unregistered files the person did not select (`other_candidate_original_ids`) without adding them. |
| `execute_analysis` | mutation | Run Core for the accepted plan and publish without another acceptance step. |
| `discard_analysis` | local mutation | Delete only an unpublished analysis workspace. |
| `preview_publication` | query | Plan recovery of a locally recorded analysis publication. |
| `apply_publication` | mutation | Apply or resume an accepted publication plan. |
| `read_document` | query | Page through a registered PDF/DOCX original or published artifact. |
| `preview_summary` | query | Validate and plan an ordered, sourced procurement summary. |
| `apply_summary` | mutation | Store an accepted summary in the manifest and `contexto.md`. |
| `list_folder` | query | List the children of the dossier root or of a folder of the tree (never `_LitMan`) with `kind`, `size`, `modified_time`, `web_view_link` and the manifest `role`. |
| `search_in_dossier` | query | Find files by accent- and case-insensitive name over the tree walk, at most 50 with `path` and `truncated`. |
| `get_file_info` | query | Metadata, `path` and the account's `can_edit`, `can_rename`, `can_move`, `can_trash`, `can_copy`, `can_download`, `can_comment` for one file of the tree. |
| `read_file` | query | Page through the text of any dossier file: PDF, DOCX, text, Markdown, CSV, XLSX, Google Docs, Sheets or Slides. |
| `list_comments` | query | List a file's comments with replies; resolved ones only with `include_resolved`. Google Docs add native threads (`source: docs`, ID `docs:<id>`, current `anchor`) to historical Drive comments (`source: drive`). |
| `preview_file_changes` | query | Resolve 1–20 protected folder/file operations (create folder, rename, move, copy, trash, export, convert) and store the accepted plan. |
| `apply_file_changes` | mutation | Apply or resume the accepted file-change plan; Drive trash is reversible and no action calls `files.delete`. |
| `preview_comment_changes` | query | Resolve 1–10 comment operations on one file (`add` with a unique exact `anchor` in a single-tab Google Doc, `reply`, `resolve`) and store the accepted plan. New comments need edit access; native and historical Drive threads go in separate plans. |
| `apply_comment_changes` | mutation | Apply the accepted comment-change plan: native Docs operations are sent once on the preview revision and reported only after a read-back proves them; historical Drive replies resume by adopting a matching reply from the active account. |
| `read_google_doc` | query | Page through the body text of a Google Doc in the dossier tree, outside `_LitMan`, with its `revision_id`. |
| `preview_document_edit` | query | Plan 1–20 closed operations on a dossier Google Doc (text edits, or paragraph, text and list styles; never both in one plan) and show each matched span with context. |
| `apply_document_edit` | mutation | Send the accepted edit as one batch guarded by the preview's revision. |
| `preview_document_creation` | query | Plan a new Google Doc in a dossier folder from text, Markdown or a dossier DOCX. |
| `apply_document_creation` | mutation | Create the accepted Google Doc and return `document_id` and `web_view_link`. |
| `preview_sheet_edit` | query | Plan 1–20 closed range operations (`update_range`, `append_rows`) on a dossier Google Sheet, with the before/after hash of each resolved range. |
| `apply_sheet_edit` | mutation | Write each accepted range only if its current values still match the preview's hash; otherwise return `conflict` (`sheet_changed`) for that range. |
| `recover` | query | Report local operation state. |
| `setup` | local mutation | Validate Core and save `codex` or `claude-code`, plus an optional model. |

The CLI form is `litman <hyphenated-operation> [--json '{...}']`. It writes the
envelope to stdout on success or stderr with exit status 2 on failure.

`litman-mcp` implements line-delimited JSON-RPC 2.0. It supports `initialize`
for protocol versions `2025-06-18`, `2025-03-26`, and `2024-11-05`,
notifications without responses, `ping`, `tools/list`, and `tools/call`.
`tools/call` returns the envelope as text and sets `isError` when `ok` is false.
`initialize` also returns Spanish server `instructions` (`SERVER_INSTRUCTIONS`
in `interfaces/mcp.py`) whose first 512 characters restrict the assistant to
LitMan tools for dossiers and Drive files and tell it to suggest asking the
developer when no tool fits. Each `tools/list` entry carries MCP
`annotations`: `readOnlyHint` is `not mutates` (so `preview_*` tools, which
only store a private local plan, count as read-only), `destructiveHint` is the
tool's `destructive` flag (`apply_incorporation`, `apply_summary`,
`apply_document_edit`, `apply_sheet_edit`, `apply_file_changes`, and
`discard_analysis`), `idempotentHint` is `true`, and `openWorldHint` is
`false`.
Protocol errors use `-32700`, `-32600`, `-32601`, and `-32602`. Services are
assembled per call, so `tools/list` works without local configuration.

`install`, `uninstall`, `login`, and `check-update` are CLI-only and are not
included in `tools/list`. Installers select only stable `vX.Y.Z` tags and do
not fall back to a branch. `litman check-update` reads the source checkout from
the private install manifest, fetches tags, and reports the newest stable
version and its changelog entries. `update_source_missing` means the existing
installation must be reinstalled once with the current installer;
`update_check_failed` means Git could not check the tags or changelog. The
`diagnose` result also includes the installed Harness `version`, without
revealing the local source path. The installed `actualizar-equipo` skill
summarizes available changes, runs the returned command on Linux, and asks the
person to close the app and run it in PowerShell on Windows. Restart the app
after the update. Older installations must run the guided installer once to
save their source checkout and install the skill.

## Core setup and execution

Before analysis, run `litman setup --json '{"provider": "codex"}'` or select
`claude-code`; `model` is optional. Setup runs `litman-core info`, checks the
public contract version and offered providers, then stores the choice in
`$XDG_CONFIG_HOME/litman-harness/settings.toml` with private POSIX permissions.
Without setup, `preview_analysis` returns `setup_required` and a recommended
setup action. Each plan snapshots its provider and model, so later setup
changes do not alter an accepted plan.

Core defaults to `gpt-5.6-luna` for Codex and `claude-sonnet-5` for Claude Code;
setup may select another model explicitly. Harness always generates the
minimal Core configuration: job type, temporary input and output directories,
and selected provider/model. It omits `job.id`, `input.kind`, and
`[publication]`, relying on the public defaults. The exact stable fields,
artifacts, errors, and versioning policy are owned by the repository
[public Core CLI contract](../../docs/contracts.md), not by Core's internal
documentation.

On Windows, Harness shortens each local original name to fit the path budget
left by the actual input directory: it keeps the `<file_id>-` prefix and the
extension (a suffix longer than 10 characters counts as part of the name) and
truncates the rest. The untouched Drive name stays in `input_snapshot.name`, so
long Drive names work with the default work root. Only when
`LITMAN_HARNESS_WORK_DIR` is so deep that not even the prefix, one character and
the extension fit does Harness return `work_path_too_long` before download; set
it to a shorter path. Harness does not depend on `LongPathsEnabled`.

## Concurrency and stale plans

All Drive writes go through the shared-state capability:

- Personal OAuth uses `DriveSharedState` and Drive API v2 `If-Match`. A read
  returns coherent content plus its ETag; an update with a stale ETag receives
  412 and never overwrites. The manifest content SHA-256 detects changes
  between preview and apply; Drive v3 `version` is not used as the shared-state
  version.
- Development metadata uses `UnavailableSharedState`, which is read-only.
  Incorporation and publication stay `planned` and return
  `pending_concurrency_gate` without writing.

Creating `manifest.json` is not atomic across independent operations. Harness
marks its create action and adopts that exact result on retry, but two truly
concurrent creations can leave duplicate manifests. Later inspection reports
`manifest_duplicated` for human repair.

Drive's `version` also changes during benign processing. Plans therefore
identify originals by `md5Checksum` and become stale only when an original's
content changes, it is trashed, or it leaves the tree. A missing MD5 returns
`missing_checksum`; the downloaded bytes are checked again against the planned
MD5. Registered folders and the live offer are checked for existence,
membership, MIME type, and capability as applicable, never Drive version.

## Recovery

Repeating a succeeded operation returns its recorded result without writing.
After `operation_interrupted`, repeating the same accepted plan skips completed
actions and searches each expected parent for operation/action markers. One
match is adopted, none is created, and multiple matches return `conflict`.

Publication merges into the current manifest. A concurrent manifest update
returns recoverable `manifest_changed_retry`; repeat the same acceptance to
resume without rerunning Core or repeating completed uploads. Incorporation is
stricter: a manifest changed since preview returns `conflict` and requires a
new preview. `recover` exposes local operation state.

A document edit that returns `conflict` with `document_changed` wrote nothing:
the document changed after the preview, or the preview's revision expired
(Docs revision IDs are valid for about 24 hours). Read the document again and
prepare a new preview. An interrupted edit or creation is resumed by repeating
the same acceptance; it never sends a second edit batch or writes a new
document's text twice. A format plan (including highlight and link) whose
answer was lost completes on that repetition if the requested formats are
visible; if the document changed in the meantime, even only its format, it
ends as `document_changed` with `write_may_have_occurred: true`: the format
may or may not have been applied, so look at the document before preparing a
new preview. Lists are not read back, so a lost answer of a plan with
`set_list` always ends that way. `docs_request_rejected` means Docs refused the
edit batch, for example a link URL it does not accept, and wrote nothing.
`partial_link_overlap` asks for the complete text of an existing link. Adding
a link gives the text Google Docs' usual link formatting, and removing it may
not restore the previous formatting.

Comment plans on Google Docs never resend a native batch once it was sent.
`comment_write_uncertain` and `comment_save_failed` carry
`write_may_have_occurred: true` and the `operation_id`: Google may have saved
some or all of the comments, but LitMan could not prove it. Repeating the same
acceptance only reads the document again and completes the operation if every
effect is now visible; it never inserts a second comment. If it stays
uncertain, a person must look at the document in Google Docs before preparing a
new plan, otherwise a comment may be duplicated. A `conflict` with
`document_changed` wrote nothing; `comment_anchor_unverified` means a comment
exists but not on the planned phrase and must be inspected. A legacy plan that
returns `comment_anchor_required` was accepted before anchors were required:
nothing of it is written, and a new plan with an `anchor` for each `add` is
needed. Existing comments are never deleted or migrated.

A sheet edit action that returns `conflict` with `sheet_changed` wrote nothing
for that range: its current values no longer match either the preview's
values or its expected result. Earlier actions of the same plan stay written;
read the sheet again and prepare a new preview for the remaining ranges.
Repeating an accepted plan after an interruption resumes action by action and
never writes an already-written range twice: a range whose current values
already match the expected result completes without a second write (a lost
answer). Sheets has no revision control, so a narrow race remains between an
action's read and its write; this is a known, accepted gap.

## Authorized validation status

Real-account checks require explicit authorization, a test folder, and actual
accounts. Test doubles do not replace them. On 2026-10-15 an authorized smoke
test covered Drive v2 `If-Match`, incorporation, context conflict and overwrite,
initial and detailed Codex analyses, publication, one converted live offer,
idempotent replay, a Haiku reader proposal, and summary application. The
converted Google Doc was reviewed visually.

Still pending:

1. Use a second authorized account and corporate OAuth client to run `login`,
   then confirm `diagnose`, `inspect`, and `status` recover the dossier by ID.
2. In real Codex App, Claude Desktop, and Claude Code installations on the
   authorized Windows device, confirm MCP discovery, `status`, and that the
   reader agent proposes a summary using only MCP reads.
3. Confirm that the configured two-hour MCP tool timeout permits a synchronous
   analysis in each real client.
4. With the Google Docs API enabled in the OAuth client's project, confirm that
   the existing `drive`-scope token can read, edit, and create dossier Google
   Docs, that `revisionId` is returned to an editor, the exact payloads of a
   disabled API and of a stale revision, and that `diagnose` reports
   `docs_api` correctly before and after enabling the API.
5. In an authorized disposable Google Doc, confirm that native anchored
   comments are visible on the intended phrase and section title, that
   `list_comments` reads, replies to and resolves them alongside a historical
   Drive comment without duplicate views, and record the exact 400 payload of a
   stale revision on a comment batch and on an edit batch (the adapter treats
   `FAILED_PRECONDITION` or a message naming the revision as
   `document_changed`, and any other 400 as `docs_request_rejected`).
6. In the same document, apply a yellow highlight to a phrase, change it to
   another `#RRGGBB` color and clear it; link a phrase to a URL, change the
   URL and remove the link. Confirm that the text, the document ID and
   neighbouring formatting and links are unchanged, that a link change on part
   of an existing link is refused, and that editing the document between
   preview and apply ends in a conflict instead of formatting other text.

The [Windows Codex app validation guide](../../docs/windows-codex-validation.md)
owns the detailed checklist, including the long-MCP-call timeout check. It is
linked here but is not maintained by this task. A local MCP smoke can use
temporary `LITMAN_HARNESS_METADATA` and send `initialize`,
`notifications/initialized`, `tools/list`, then an `inspect` `tools/call`
over stdin.

New detailed analyses produce `propuesta_tecnica.docx`. Repeated uploads may gain
a date suffix; the converted Google Doc initially named `propuesta_tecnica` can
be renamed without losing its ID-based live-offer registration. Existing files
and Google Docs keep their names.
