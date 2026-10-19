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

## Operations

CLI and MCP return the same envelope: `{"ok": true, "result": ...}` or
`{"ok": false, "error": {"code", "message", "details"}}`. Input is validated
against each operation's `inputSchema`, including required fields, types,
enums, and rejection of extra properties; invalid input returns
`invalid_request`.

| Operation | Kind | Responsibility |
| --- | --- | --- |
| `identity` | query | Report the active account. |
| `diagnose` | query | Report adapters, identity, scopes, Core contract/environment/provider, shared-state mechanism, guided-install state, and whether configured paths exist, never tokens or paths. |
| `inspect` | query | Inventory the connected folder tree, candidates, suggestions, and next actions. |
| `status` | query | Combine inspection with manifest status, pending local publications, and `recommended_action`. |
| `preview_incorporation` | query | Plan only missing folders, originals, live offer, context, and manifest work. |
| `apply_incorporation` | mutation | Apply the accepted incorporation `plan_id`. |
| `preview_analysis` | query | Plan Core analysis and publication with the provider fixed by `setup`. |
| `execute_analysis` | mutation | Run Core for the accepted plan and publish without another acceptance step. |
| `discard_analysis` | local mutation | Delete only an unpublished analysis workspace. |
| `preview_publication` | query | Plan recovery of a locally recorded analysis publication. |
| `apply_publication` | mutation | Apply or resume an accepted publication plan. |
| `read_document` | query | Page through a registered PDF/DOCX original or published artifact. |
| `preview_summary` | query | Validate and plan an ordered, sourced procurement summary. |
| `apply_summary` | mutation | Store an accepted summary in the manifest and `contexto.md`. |
| `recover` | query | Report local operation state. |
| `setup` | local mutation | Validate Core and save `codex` or `claude-code`, plus an optional model. |

The CLI form is `litman <hyphenated-operation> [--json '{...}']`. It writes the
envelope to stdout on success or stderr with exit status 2 on failure.

`litman-mcp` implements line-delimited JSON-RPC 2.0. It supports `initialize`
for protocol versions `2025-06-18`, `2025-03-26`, and `2024-11-05`,
notifications without responses, `ping`, `tools/list`, and `tools/call`.
`tools/call` returns the envelope as text and sets `isError` when `ok` is false.
Protocol errors use `-32700`, `-32600`, `-32601`, and `-32602`. Services are
assembled per call, so `tools/list` works without local configuration.

`install`, `uninstall`, and `login` are CLI-only and are not included in
`tools/list`.

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

If an analysis work path would be too deep on Windows, Harness returns
`work_path_too_long` before download. Set `LITMAN_HARNESS_WORK_DIR` to a shorter
path; Harness does not depend on `LongPathsEnabled`.

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

The [Windows Codex app validation guide](../../docs/windows-codex-validation.md)
owns the detailed checklist, including the long-MCP-call timeout check. It is
linked here but is not maintained by this task. A local MCP smoke can use
temporary `LITMAN_HARNESS_METADATA` and send `initialize`,
`notifications/initialized`, `tools/list`, then an `inspect` `tools/call`
over stdin.
