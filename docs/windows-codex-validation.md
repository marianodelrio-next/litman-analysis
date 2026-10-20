# Windows Codex app validation guide

Manual checks for installing and operating LitMan with the **Codex app on
native Windows 10/11**. These checks cannot run in CI: they need a real
Windows machine, the Codex app signed in with a real account, and in some
steps an authorized Google Workspace test account and OAuth client. This
guide replaces the two prior Spanish manual-validation documents, which mixed
platforms and providers and did not state expected outputs.

Use only authorized test accounts and an authorized test Drive folder — never
production data. Do not record tokens, full private paths, or tender content
in notes or screenshots; record relative paths and non-sensitive evidence
only.

Product strings shown on screen (installer messages, error messages, skill
phrases) are quoted below exactly as the code prints them, in Spanish. The
surrounding guide text is in English.

Each numbered step gives the action, the exact command or UI action, and the
expected output. An expected output marked **observe and record** cannot be
derived from the code; write down what actually happens instead of assuming
the text below.

## 0. Readiness checklist

Confirm all of the following before starting:

- The code for CHG-0003, CHG-0005, and CHG-0006 is merged into the remote `master`. The guided
  install one-liner installs the latest `v*` tag if one exists, otherwise
  `origin/HEAD` (`harness/deployment/install.ps1`), so without a tag it
  installs whatever is on `master` at the time.
- A Windows 10 or 11 machine.
- The Codex app installed and signed in with a personal-plan test account.
- Git and uv installed.
- Microsoft Edge and/or Google Chrome installed.
- A Google Workspace test account that is **not** the Workspace admin
  account.
- The internal-audience OAuth `client_secret.json`, delivered through the
  usual secure channel (never a repository link).
- An authorized test Drive folder containing a synthetic tender with Spanish
  names and text (`PCAP`, `anuncio`, `adjudicación` in file names) and two
  files that share the same visible name but have different Drive file IDs.
- Access to the Google Cloud project that owns the OAuth client, to enable
  and disable the Google Docs API (section 8), or someone who administers it.
- A short, disposable working directory for this run.

Record, without including sensitive content: Windows edition and version,
Codex app version, `codex --version`, Git version, uv version, Python
version, and the installed `litman`/`litman-core` versions, plus the resolved
paths the steps below ask for (not their contents).

## 1. Missing prerequisites

Simulate each case in a PowerShell session with a trimmed `$env:PATH` so the
tool under test is not found, then run the guided install command from
section 2 for that case only.

- **No Git.** Expected: the script stops before doing anything else and
  prints `Falta Git. Instalelo desde: https://git-scm.com/downloads/win`,
  exits non-zero, and installs nothing.
- **No uv.** Expected: the script stops and prints
  `Falta uv. Ejecute usted mismo:` followed by
  `irm https://astral.sh/uv/install.ps1 | iex` and the link
  `https://docs.astral.sh/uv/getting-started/installation/`; it exits
  non-zero without installing uv itself.
- **No `codex` CLI on `PATH`** (Git and uv present). Expected: the script
  checks for `codex` right after the uv check — before cloning the
  repository or running `uv tool install` — and stops with
  `Falta la CLI de Codex. Instalela siguiendo:` followed by
  `https://github.com/openai/codex`; the repository is not cloned and no
  `uv tool install` runs.

## 2. Install with the README one-liner

Action: paste the Codex one-liner from `harness/deployment/README.md` into a
plain PowerShell session (not elevated).

Command:

```powershell
$env:LITMAN_APP='codex'; irm https://raw.githubusercontent.com/marianodelrio-next/litman-analysis/master/harness/deployment/install.ps1 | iex
```

Expected output: the script clones or updates the repository under
`%LOCALAPPDATA%\LitMan\src`, checks out the latest `v*` tag or `origin/HEAD`,
runs `uv tool install --force --python 3.11` for `harness` with `core`, reads
`uv tool dir` as UTF-8, runs the Harness CLI through the tool environment's
interpreter (`& $Python -m litman_harness.interfaces.cli install --app codex
--source <repo>`, where `$Python` is
`<uv tool dir>\litman-harness\Scripts\python.exe`; it never runs the uv
`litman.exe` launcher), and prints:

```
Instalacion completa. Para terminar:
  1. Cierre y vuelva a abrir la aplicacion.
  2. Abra la carpeta LitMan (%USERPROFILE%\LitMan).
  3. Escriba: prepara mi equipo
```

**Observe and record:** the exact window/exit behavior of `irm | iex` when
the script fails partway through (whether the PowerShell window stays open
and whether the error is visible).

Check: on a profile whose path contains an accented character (for example
`C:\Users\María Núñez`) and with Smart App Control on, the install
completes without manual workarounds. `%USERPROFILE%\LitMan\AGENTS.md`
gives the `litman` command as
`& "<uv tool dir>\litman-harness\Scripts\python.exe" -m litman_harness.interfaces.cli`,
and "prepara mi equipo" runs `install --oauth-client` and `login` through
that command.

Action: restart the Codex app, open the `%USERPROFILE%\LitMan` folder, and
type **"prepara mi equipo"**.

Expected output: the `preparar-equipo` skill starts and runs its steps in
order (see sections 3–5 below for what each step does).

## 3. Codex CLI and session

- **Observe and record** whether the Codex app installation puts `codex` on
  `PATH` by itself, or whether a separate CLI install is needed.
- **Observe and record** whether the Codex session lives at
  `%USERPROFILE%\.codex\auth.json` or in the Windows credential store, and
  whether it is shared between the app and the CLI.

## 4. Contract and environment

Action: run Core's own `info` command directly.

Command: `litman-core info`

Expected output: a single JSON object with `contract: 1`, for example:

```json
{"contract": 1, "version": "0.1.0", "providers": ["claude-code", "codex"],
 "environment": {
   "providers": {"codex": {"cli": true, "session": true},
                 "claude-code": {"cli": false, "session": false}},
   "pdf_browser": true}}
```

`environment` is optional and local-only (binary on `PATH`, a session file, a
discoverable PDF browser); it never runs a provider CLI or opens a browser.
`false` means "not detected", not necessarily "absent". If `pdf_browser` is
`false`, note it — it is a non-blocking warning, not a failure, from the
`preparar-equipo` skill's point of view.

Action: run the harness diagnostics operation.

Command: `litman diagnose`

Expected output: a JSON envelope `{"ok": true, "result": {...}}` covering the
configured adapter, OAuth scopes, `litman-core` (including its environment
check above), the concurrency gate, the Google Docs API state (`docs_api`:
`enabled`, `disabled`, or `unknown`), configured paths, and the installation
status (`litman install`), without tokens, secrets, or local paths. Before
`litman login`, `docs_api` is `unknown`.

Action: run setup with the Codex provider.

Command: `litman setup --json '{"provider": "codex"}'`

Expected output: `{"ok": true, "result": {...}}` after `setup` validates
`litman-core info` and records the provider (and model, if given) for this
installation.

Confirm: harness state (manifest, settings, token, OAuth client) lives under
`%LOCALAPPDATA%\litman-harness`. If `LITMAN_HARNESS_WORK_DIR`,
`LITMAN_HARNESS_METADATA`, `LITMAN_HARNESS_OAUTH_TOKEN`,
`LITMAN_HARNESS_OAUTH_CLIENT`, `LITMAN_HARNESS_PLAN_STORE`, or `CODEX_HOME`
are set explicitly in the environment, confirm the harness honors those paths
instead of the defaults.

## 5. OAuth client and second account

Action: install the OAuth client delivered through the secure channel.

Command: `litman install --oauth-client <path to client_secret.json>`

Expected output: `{"ok": true, "result": {"oauth_client": {...}}}`; the file
is copied with private permissions into harness state; the original file at
`<path>` is deleted only if `--delete-original` was passed **and** you
explicitly confirmed you wanted it deleted.

Action: sign in with the second Workspace test account.

Command: `litman login`

Expected output: opens the browser for the account picker; on success,
`{"ok": true, "result": {...}}`. If the local loopback callback fails,
**observe and record** whether a firewall or Windows machine policy is
blocking loopback traffic.

Action: confirm the session recovers a test dossier by ID.

Commands: `litman diagnose`, then the `inspect` and `status` operations for
that dossier (via MCP from the app, or `litman inspect --json '{...}'` /
`litman status --json '{...}'` if exposed through the CLI harness you are
using).

Expected output: `status` reports one of `unadopted`, `partial`, `adopted`,
`degraded`, or `unsupported_manifest`, plus `next_actions`; `inspect` reports
the folder inventory and its own `next_actions`.

Confirm: because the OAuth client is configured for internal audience, no
"unverified app" Google warning appears during login, and the token does not
expire after 7 days — repeat `diagnose` a few days later to confirm.

**Observe and record:** the effective Windows ACLs (not Unix permission
bits) of the harness state directory, `settings.toml`, `token.json`, and
`%USERPROFILE%\.codex\auth.json`, without copying their contents. Confirm
they inherit from the expected user profile and are not broadly readable.

## 6. Analysis from the app

- **Originals placement.** Connect a test dossier whose tender PDFs sit in
  its root and accept the incorporation. **Observe and record** the
  `canMoveItemWithinDrive` and `canCopy` capabilities that `get` reports for
  those PDFs with the person's real role, and the `place_original` strategy
  the preview shows (`move`, `copy`, or `in_place`). Expected after applying:
  with `move`, each PDF is in `Originales` with the same ID; with `copy`, a
  copy with the same name is in `Originales`, its `md5Checksum` equals the
  source's, the manifest registers it with `copied_from`, the source stays in
  the root, and `placement_warnings` explains it; with `in_place`, the PDF stays
  where it is with `placement: "in_place"` and a warning. Nothing is deleted
  or trashed in any case.
- **Reader subagent.** The `lector-licitacion` subagent is configured with
  `model = "gpt-5.6-luna"`, `model_reasoning_effort = "low"`, and
  `sandbox_mode = "read-only"`, using only the `status` and `read_document`
  MCP tools. Invoke it from the Codex app on a synthetic tender and confirm
  it runs; there is a community report of "unknown agent_type" when invoking
  custom subagents from the Codex desktop app — confirm whether it reproduces
  here. Confirm the configured model is available on the personal-plan test
  account.
- **Long MCP call.** The MCP `litman` server is registered with a two-hour
  tool timeout (`tool_timeout_sec = 7200` for Codex). Separately, Core's own
  Codex subprocess has an internal 30-minute timeout
  (`timeout_seconds = 1800` in `codex_cli.py`) before it raises
  `CodexTimeoutError`. Run an analysis that takes several minutes and confirm
  the MCP call is not cut at the default ~60s. **Observe and record**
  whether a run between 30 minutes and 2 hours is cut by Core's internal
  30-minute timeout even though the MCP layer would otherwise tolerate 2
  hours — do not assume the full two hours are usable end to end.
- **Unicode through pipes.** Run a synthetic job whose name and text contain
  `ñ`, accented vowels, and a character outside cp1252. The harness sets
  `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8` for the Core child process.
  Confirm the JSON read back by the harness has no substituted characters in
  names, errors, or artifacts.
- **File names, `input_snapshot`, and hashes.** Use test originals named with
  `PCAP`, `anuncio`, and `adjudicación`, plus the two same-visible-name
  originals from the readiness checklist. Confirm each `input_snapshot` entry
  has `file_id`, `name`, `local_name`, `drive_version`, `md5_checksum`,
  `sha256`, and `size`; confirm the two same-visible-name originals get
  distinct `local_name` values (each prefixed with its `file_id`) and neither
  overwrites the other. A true `local_name` collision raises
  `local_name_collision`.
- **Long Drive names.** With `LITMAN_HARNESS_WORK_DIR` unset, analyse a
  dossier with an original whose Drive name exceeds 100 characters. Expected:
  the analysis succeeds; its `local_name` is shortened (keeping the
  `<file_id>-` prefix and the extension) while `name` keeps the full Drive
  name.
- **Deep work path.** Configure a very deep `LITMAN_HARNESS_WORK_DIR` so that
  not even `<file_id>-`, one character and the extension fit within Windows'
  260-character limit with margin. Expected: an early error,
  `work_path_too_long` — *"La ruta de trabajo es demasiado larga; configure
  LITMAN_HARNESS_WORK_DIR con una ruta más corta"* — before any partial
  download is treated as published. Do not enable `LongPathsEnabled` to make
  this check pass; it must fail with a short path.
- **PDF with Edge/Chrome.** With both installed, generate a tender summary
  PDF. **Observe and record** which executable is chosen, that the PDF opens
  and contains the Spanish characters correctly, and that it respects the
  page limit. Repeat with a path containing spaces, and force a controlled
  browser failure to confirm the diagnostic is readable even if it includes
  characters outside the local code page. Finding `msedge.exe` on disk does
  not by itself prove headless printing works on that version — run it.
- **Codex native session and events.** Confirm whether the test session is
  at `%USERPROFILE%\.codex\auth.json` or the OS credential store (see section
  3), run an analysis using the supported authentication mode, and review the
  Codex events and the tools actually executed.

## 7. Publish and discard

- Complete a local analysis on the synthetic tender, then either publish it
  (preview and apply publication) or discard it.
- **Flat layout.** After publishing, **observe and record** that the artifacts
  sit directly in `Analisis inicial` (or `Analisis detallado`) with no dated
  subfolder, and that the result's `folder_id` is that folder. Run and publish
  the same analysis type again and confirm the new files carry the date suffix
  (`ficha_oportunidad (YYYY-MM-DD).pdf`) while the earlier files are unchanged.
- **Discard with a locked file.** Open a file inside that analysis's local
  workspace in another program, then discard the analysis. Expected output
  today: an `internal_error` envelope (`"Fallo inesperado del harness"`) —
  `remove_workspace()` lets the underlying `OSError`/`PermissionError`
  propagate uncaught through `discard()`, and the generic exception handler
  in the tool-invocation layer turns it into `internal_error`. Because
  `discard()` never finishes, the operation record stays at its previous
  status and remains recoverable — it is not reported as discarded while the
  file is still locked. This is a known limitation of the current discard
  path, not a bug to fix in this guide; record it as-is.

## 8. Google Docs: read, edit, conflict, and create

Run these steps on the real account after section 7, against the live offer
(the Google Doc in `Oferta`) of the synthetic tender. They also settle the
open questions of CHG-0006: whether the `drive`-scope token is accepted by the
Docs API, the exact error payloads, and whether `revisionId` is returned.

- **Disabled API.** With the Google Docs API disabled in the OAuth client's
  Cloud project, run `litman diagnose`. Expected output: `docs_api` is
  `disabled`. Ask the app to read the technical proposal. Expected output: the
  assistant explains that the administrator must enable the Google Docs API
  (`docs_api_disabled`, message *"La API de Google Docs no está habilitada: el
  administrador debe habilitar la Google Docs API en el proyecto de Google
  Cloud del cliente OAuth"*) and does not open a browser. **Observe and
  record** the HTTP 403 reason Google returns.
- **Enabled API.** Enable the Google Docs API in APIs & Services > Library,
  wait a few minutes, and run `litman diagnose` again without logging in
  again. Expected output: `docs_api` is `enabled`. If it stays `unknown` or
  the next steps return `insufficient_permission`, **observe and record** the
  response: the `drive` scope may not be accepted and the design needs a
  decision.
- **Read.** In the app, type *"lee la propuesta técnica de la licitación"*.
  Expected output: the assistant calls `read_google_doc` and summarizes the
  text; the result carries a non-null `revision_id` (**observe and record**
  whether it is returned to an editor).
- **Edit.** Ask the app to replace one sentence of the proposal that contains
  accents (`á`, `ñ`) and to append one line at the end. Expected output: the
  assistant shows the `preview_document_edit` result, with each matched span
  and its context, and waits for your answer. After you accept,
  `apply_document_edit` returns `succeeded`; open the document in Google Docs
  and confirm both changes, with the formatting of the surrounding paragraph
  and nothing else changed. At no point does the assistant use computer use or
  a browser.
- **Conflict.** Ask for another edit and stop at the preview. Change any text
  in the document by hand in Google Docs, then accept the preview. Expected
  output: `conflict` with code `document_changed` and nothing written by
  LitMan; the assistant offers to read the document again. **Observe and
  record** the HTTP status and payload Docs returns for the stale revision.
- **Create from text.** Ask the app to create a Google Doc named
  `Prueba LitMan` in `Oferta` with two short paragraphs. Expected output: a
  preview, then after you accept a `document_id` and `web_view_link`; the
  document contains the two paragraphs once. Asking for the same name again
  returns `name_exists`.
- **Create from DOCX.** Ask the app to create a Google Doc from a DOCX of the
  tender. Expected output: a converted Google Doc in the chosen folder, the
  DOCX unchanged.

## 9. Repair

Action: delete the token (`token.json`) under the harness state directory,
then type **"prepara mi equipo"** in the app again.

Expected output: the skill's first step, `diagnose`, detects the missing
session and the skill addresses only that failing step (OAuth/login), per
`preparar-equipo`'s repair behavior, rather than repeating the whole setup.

## 10. Uninstall

Action: open a file inside the LitMan workspace folder in another program,
then run the uninstall script requesting workspace removal.

Command:

```powershell
$env:LITMAN_REMOVE_WORKSPACE='1'; harness\deployment\uninstall.ps1
```

Expected output: the script reads `uv tool dir` as UTF-8 and, if the tool
environment's `python.exe` exists, runs
`& $Python -m litman_harness.interfaces.cli uninstall --remove-workspace`
(not the uv `litman.exe` launcher). That `litman uninstall --remove-workspace`
call returns a `failed`
list that includes the locked item; because `failed` is non-empty, `litman
uninstall` prints an error envelope with code `uninstall_incomplete` and
message *"No se pudieron eliminar algunos elementos. Cierre los programas que
puedan estar usando esos archivos o carpetas y vuelva a ejecutar la
desinstalación."*, with `removed`/`kept`/`failed` in `details`, and exits 2;
`uninstall.ps1` checks `$LASTEXITCODE` right after that call and exits with
it, **before** running `uv tool uninstall litman-harness` and before
deleting the local source checkout. Codex, Git, and uv themselves are left
untouched, and the installation manifest is kept (it is only deleted when
`failed` is empty).

Action: close the program holding the file, then run the same command again.

Expected output: this time `failed` is empty, the manifest is deleted,
`uv tool uninstall litman-harness` runs, the local source checkout is
removed, and the script prints `LitMan desinstalado.`. The LitMan folder
itself (`%USERPROFILE%\LitMan`) is removed only because
`LITMAN_REMOVE_WORKSPACE=1` was requested; without it, uninstall keeps the
folder, the OAuth client and token, and private data by default.

## 11. Run both test suites natively

Action: from a native PowerShell session (no WSL), run each package's tests.

Commands:

```powershell
cd core; uv run pytest -q
cd ..\harness; uv run pytest -q
```

Expected output: both suites pass. Record any skipped test and why.

## 12. Results and reporting

For each system, app, and provider combination exercised, record: system and
version, step executed, result, non-sensitive local evidence, and whether a
failure is reproducible. If a step fails, open a scoped fix, rerun the
affected suite on both Ubuntu and Windows, and update this guide.

## Pending decision

Using `--dangerously-bypass-approvals-and-sandbox` (Core's current Codex
invocation flag, in `codex_cli.py`) outside Docker isolation needs an
explicit decision on acceptable sandboxing before it is used for real
analyses on a native Windows installation. This guide does not make that
decision; it only exercises the flow as currently implemented.

## Deferred (not part of this run)

- Validating the update flow through a published `v*` tag.
- A CI matrix for `ubuntu-latest` and `windows-latest`.
- Claude Desktop installation and validation.
- Ubuntu desktop validation (covered separately, not by this Windows guide).
- Claude Code native CLI checks (`claude.exe`, `assessment`,
  `detailed-analysis`, `--restricted`/`--permission-mode`/`--tools` flags).
