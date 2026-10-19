# CHG-0003 — Reliable uninstall reporting and a single Windows Codex app validation guide

## Context
Verified on `master` at `854dfcf`:

- `harness/src/litman_harness/installation.py` `uninstall()` (around lines 285–381) removes skill
  folders, the LitMan workspace folder and the plan/work data roots with
  `shutil.rmtree(..., ignore_errors=True)` and then appends the item to `removed` unconditionally.
  Single files (`subagent`, `CLAUDE.md`, OAuth client, token, settings) use `unlink()` with no error
  handling. At the end it always deletes the install manifest (`manifest_path(env).unlink(...)`).
  On Windows a file held open by another process makes `rmtree` silently leave the folder in place
  while the result still says `removed`, and the manifest needed to retry is gone.
- `harness/src/litman_harness/interfaces/cli.py` `uninstall()` always returns
  `{"ok": True, "result": result}` unless a `HarnessError` is raised; `main()` exits 2 only when
  `ok` is false.
- `harness/deployment/uninstall.sh` (`set -eu`) and `uninstall.ps1`
  (`$ErrorActionPreference = 'Stop'`) run `litman uninstall`, then always run
  `uv tool uninstall litman-harness`, delete the source clone and print `LitMan desinstalado.`.
  `uninstall.ps1` does not check `$LASTEXITCODE` after `& $LitmanBin uninstall`, so a native
  non-zero exit does not stop it.
- `harness/deployment/install.sh` and `install.ps1` check Git and uv first, then clone/fetch the
  repository into the source directory, run `uv tool install ...`, and only then check the provider
  CLI (`codex`/`claude`). Without the CLI the script exits 1 but has already cloned the repository
  and installed `litman`, `litman-mcp` and `litman-core`.
- The analysis discard path (`harness/src/litman_harness/analysis/service.py`, `discard()` →
  `remove_workspace()`, around lines 185–252) lets non-read-only deletion errors propagate; a
  locked file surfaces through the tool layer as `internal_error` and the operation is not marked
  discarded (it stays recoverable). This change does not alter it; the guide documents it.
- Manual validation is split across `docs/validacion_manual_instalacion.md` (installation,
  Windows + Ubuntu, Codex + Claude) and `docs/windows_manual.md` (native Windows compatibility of
  Core/harness). They overlap, mix platforms and apps, and do not say what output to expect at each
  step. On `master` they are referenced from `core/README.md`, `harness/docs/development.md`
  (twice; one link points to "§1", the MCP timeout check) and from each other.
- Change **CHG-0002** (awaiting approval) translates and reorganizes the rest of the docs. It
  excludes these two manuals from its patches but keeps links to them valid, and may move the
  `harness/docs/development.md` references into new files such as `harness/docs/operations.md`.
- Existing tests: `harness/tests/test_installation.py` (uninstall tests around lines 223–352,
  including `test_uninstall_without_manifest_is_a_noop`, which asserts the exact result
  `{"removed": [], "kept": []}`), `harness/tests/deployment/test_install_script.py` (runs
  `install.sh` with fake binaries on a trimmed `PATH`; `install.ps1`/`uninstall.ps1` are checked by
  content because there is no `pwsh` on the dev machine).

## Goal and scope
In scope:
1. `uninstall()` reports only what was really removed, lists what could not be removed, keeps the
   manifest when anything failed, and `litman uninstall` plus both uninstall scripts stop with an
   error instead of claiming success, so the person can close the locking program and retry.
2. Both install scripts check the provider CLI right after the uv check, before cloning or
   installing anything.
3. A new, single, step-by-step validation guide for the **Codex app on native Windows 10/11**,
   in English, replacing both existing manual documents.

Out of scope: release tags/versioning, CI, asynchronous analysis, Claude Desktop and Ubuntu
validation, the Codex `--dangerously-bypass-approvals-and-sandbox` isolation decision (the guide
lists it as a pending decision), changing discard behaviour on locked files, product prompts,
schemas, templates and pipelines. The guide assumes MCP tool calls survive long runs (the person
decided this); the timeout check is an ordinary step, not a gate.

## Acceptance criteria
- AC-01: Given an installed manifest, when removing a recorded folder or file raises `OSError`,
  then `installation.uninstall()` puts that item in a `failed` list (not in `removed`), still
  processes the remaining items, and keeps the install manifest; a second `uninstall()` after the
  cause is gone removes the rest and deletes the manifest; when nothing fails the result has
  `failed: []` and the manifest is deleted as today; the no-manifest result is
  `{"removed": [], "kept": [], "failed": []}` — verified by: new and updated tests in
  `harness/tests/test_installation.py` (at least one folder failure, e.g. `workspace` or
  `skill:<name>`, and one file failure, e.g. `token`).
- AC-02: Given a non-empty `failed` list, when `litman uninstall` runs, then it emits an error
  envelope with code `uninstall_incomplete` whose details include `removed`, `kept` and `failed`,
  and exits 2; `uninstall.sh` stops before `uv tool uninstall` and before deleting the source clone
  (because of `set -e`), and `uninstall.ps1` checks `$LASTEXITCODE` right after
  `& $LitmanBin uninstall` and exits with it before `uv tool uninstall` — verified by: a CLI test
  (e.g. in `harness/tests/interfaces/test_transports.py` or `harness/tests/test_installation.py`), a
  `uninstall.sh` test with fake binaries, and a content-order test for `uninstall.ps1`.
- AC-03: Given `LITMAN_APP=codex` (or `claude`) and no matching CLI on `PATH`, when the install
  script runs, then it exits non-zero printing the official CLI link, without cloning the
  repository and without `uv tool install` — verified by: an `install.sh` test using the fake-`PATH`
  pattern that asserts the link in the output (`https://github.com/openai/codex` or
  `https://docs.claude.com/en/docs/claude-code/setup`), that the source directory was not created,
  and that a fake `uv` logged no `tool install`; and a content-order test for `install.ps1` that the
  `Get-Command codex` / `Get-Command claude` checks appear before both `git` clone and
  `uv tool install`.
- AC-04: `docs/validacion_manual_instalacion.md` and `docs/windows_manual.md` no longer exist, the
  new guide `docs/windows-codex-validation.md` exists, and no tracked file outside `.factory/` and
  `dist/` references the old names — verified by:
  `bash -lc 'test ! -e docs/validacion_manual_instalacion.md && test ! -e docs/windows_manual.md && test -f docs/windows-codex-validation.md && ! grep -rIl --exclude-dir=.factory --exclude-dir=dist --exclude-dir=.git -e validacion_manual_instalacion -e windows_manual .'`.
- AC-05: The guide is in English, covers every item of the coverage list in Implementation notes,
  starts with a readiness checklist, and each numbered step states the action, the exact command or
  UI action, and the expected output; expected outputs that come from the code (script messages,
  JSON fields, error codes, file paths) match the code after CHG-0003-01, and outputs that cannot
  be derived from the code are marked "observe and record" instead of invented — verified by:
  manual conformance review against the code.
- AC-06: Core and harness suites pass — verified by:
  `bash -lc 'cd core && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'` and
  `bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'`.

## Approach
- **Uninstall core logic:** add one small private helper in `installation.py` that removes a file or
  a tree and returns `True`/`False`, catching `OSError`. On Windows it retries read-only files like
  `_remove_readonly` in `analysis/service.py`; copy that three-line callback into `installation.py`
  rather than importing `analysis.service` (which would pull Drive/analysis modules into
  installation). Every filesystem removal site (skills, subagent, `CLAUDE.md`, workspace, OAuth
  client, token, settings, data roots) uses the helper and appends to `removed` or `failed` with
  the existing item names. The manifest is deleted only when `failed` is empty. Existence checks
  stay, so retrying is a no-op for items already removed. The Codex config rewrite
  (`_atomic_write`), the Claude settings write (`write_private`) and `claude mcp remove` keep their
  current behaviour; an `OSError` there still aborts uninstall with the manifest kept, which is
  accepted.
- **CLI and scripts:** `cli.uninstall()` returns
  `error_envelope("uninstall_incomplete", <Spanish message telling the person to close programs
  using those files and run the uninstall again>, result)` when `result["failed"]` is non-empty;
  `main()` already exits 2. `uninstall.sh` needs no change beyond relying on `set -e` (verify by
  test); `uninstall.ps1` gains `if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }` after the
  `& $LitmanBin uninstall` call. Alternative considered: raising on the first failure — rejected
  because it leaves the rest installed without a list of what remains.
- **Install scripts:** move the existing provider CLI block, unchanged in wording, to right after
  the uv check and before the source directory/clone step, in both scripts.
- **Guide:** written from scratch rather than merging, because the old documents mix Ubuntu,
  Claude and Codex and lack expected outputs. Order:
  0. Readiness checklist (all true before starting): code of CHG-0003 merged into the remote
     `master` (the one-liner installs the latest `v*` tag, none exists, so it installs
     `origin/HEAD`); Windows 10/11 machine; Codex app installed and signed in with a personal-plan
     test account; Git and uv installed; Edge and/or Chrome; a Google Workspace test account (not
     the admin); the internal-audience OAuth `client_secret.json` delivered through the usual
     secure channel; an authorized test Drive folder with a synthetic tender (Spanish names and
     text, `PCAP`/`anuncio`/`adjudicación` names, two files with the same visible name); a short
     disposable working directory. What to record (Windows edition/version, Codex app version,
     `codex --version`, Git, uv, Python, `litman`/`litman-core` versions, resolved paths) and the
     privacy rules (no tokens, full private paths or tender content in notes).
  1. Missing prerequisites, simulated in a PowerShell session with a trimmed `$env:PATH`: no Git,
     no uv, no `codex` → each stops with its official link and installs nothing.
  2. Install with the README one-liner, restart the app, open `LitMan`, "prepara mi equipo".
     The `irm | iex` exit/window behaviour on errors is "observe and record".
  3. Codex CLI and session: whether the app puts `codex` on `PATH`, where the session lives
     (`%USERPROFILE%\.codex\auth.json` or the OS credential store).
  4. Contract and environment: `litman-core info` (`contract: 1`), `litman diagnose`,
     `litman setup`; state under `%LOCALAPPDATA%\litman-harness`; explicit
     `LITMAN_HARNESS_*`/`CODEX_HOME` still honoured.
  5. OAuth: `litman install --oauth-client`, `litman login`, loopback callback, `diagnose`,
     `inspect`, `status`; no "unverified app" warning; profile ACLs of state dir, `settings.toml`,
     `token.json`, `CODEX_HOME\auth.json`; repeat `diagnose` days later (token not expiring at 7
     days).
  6. Analysis from the app: `lector-licitacion` subagent invocation (watch for
     "unknown agent_type") and `gpt-5.6-luna` availability; a long MCP call; Unicode through pipes;
     file names, `input_snapshot` and hashes, duplicate visible names; deep work path →
     `work_path_too_long`; PDF with Edge/Chrome (which executable, Spanish characters, page limit,
     path with spaces, controlled browser failure readable); Codex events and executed tools
     reviewed.
  7. Publish and discard; discard with a locked file → current expected output `internal_error`
     and the operation stays recoverable (known limitation, record it).
  8. Repair: delete the token; `preparar-equipo` detects it with `diagnose` and guides the missing
     step.
  9. Uninstall: first with a file in the workspace held open (with workspace removal requested) →
     `uninstall_incomplete` listing `failed`, Codex/Git/uv untouched; close it and retry → success;
     the LitMan folder is removed only when requested.
  10. Run both test suites in native PowerShell (`uv run pytest -q` from `core/` and `harness/`),
      recording skipped tests and why.
  11. Results table (system, version, step, result, non-sensitive evidence, reproducible failure)
      and how to report a failure (scoped fix, rerun on Ubuntu and Windows, update the guide).
  Closing sections: pending decision (Codex sandbox bypass outside Docker before real use) and
  deferred items not part of this run (update via `v*` tag, CI matrix, Claude Desktop, Ubuntu,
  Claude Code native check).
- No ADR: no architecture or public contract decision; `failed` and `uninstall_incomplete` belong
  to a CLI-only command used by the install scripts.

## Implementation notes
- **CHG-0003-01** touches `harness/src/litman_harness/installation.py`,
  `harness/src/litman_harness/interfaces/cli.py`, `harness/deployment/install.sh`, `install.ps1`,
  `uninstall.ps1` (and `uninstall.sh` only if a test shows it is needed), their tests, and
  `harness/deployment/README.md` if it describes uninstall results. Follow the test style in
  `harness/tests/test_installation.py` (tmp `home`, `monkeypatch`, manifest written by a real
  `install()` call). Simulate failures with `monkeypatch.setattr` on the new helper or on
  `installation.shutil.rmtree` / a specific `Path.unlink` target, never by patching the global
  `shutil.rmtree` (pytest's tmp cleanup uses it) and never by relying on OS locking. Update
  `test_uninstall_without_manifest_is_a_noop` for the new `failed` key. For `install.sh`/
  `uninstall.sh`, follow `test_without_uv_stops_with_the_official_command` and
  `test_install_sh_end_to_end_then_idempotent_then_uninstall` in
  `harness/tests/deployment/test_install_script.py`; for `.ps1`, extend the content test style of
  `test_install_and_uninstall_ps1_contain_the_official_links_and_no_elevation` with index-order
  assertions. User-facing messages stay in Spanish like the existing ones.
- **CHG-0003-02** writes `docs/windows-codex-validation.md` in English. Product strings shown on
  screen (installer messages, `HarnessError` messages, skill phrases such as "prepara mi equipo")
  stay quoted literally in Spanish. Take expected outputs from: `install.ps1`, `uninstall.ps1`,
  `interfaces/cli.py`, `interfaces/tools/__init__.py` (`internal_error`), `installation.py`,
  Core `info` (`docs/contracts.md`, `docs/contracts/`), `harness/agent/skills/preparar-equipo/SKILL.md`,
  `harness/agent/codex/agents/lector-licitacion.toml`, `analysis/inputs.py`, `analysis/service.py`,
  `local_paths.py`, `adapters/core.py`, and `core/src/litman_core/infrastructure/llm/codex_cli.py`.
- **Coverage list (AC-05):** from `validacion_manual_instalacion.md` items 1–12, 14–16 and 18–19
  restricted to the Codex app on Windows (item 11 keeps only its Windows part; item 13 is
  Claude-only and item 17 needs a `v*` tag, both go to deferred); from `windows_manual.md` the
  preparation steps (record versions, run both suites in native PowerShell) and items 1–5 and 7–10
  (item 6 is Claude-only and goes to deferred).
- **Links:** find references by content (`grep -rn -e validacion_manual_instalacion -e windows_manual`),
  not by line number, and point each one to the new guide; the `development.md` "§1" link (MCP
  timeout) points to the guide's long MCP call step in section 6. Add the guide to
  `docs/README.md` if that index exists (CHG-0002 creates it). `docs/codebase-map.md` lists `docs/`
  only as a whole: do not change it.
- **Ordering with CHG-0002:** implement CHG-0003-02 after CHG-0002 is merged, so CHG-0002's link
  checks (its AC-08) run while the old manuals still exist and this task then retargets the links
  in their final, translated locations. If CHG-0002 is not merged when CHG-0003-02 starts, stop and
  ask the person rather than editing files CHG-0002 is rewriting.

## Tasks
```yaml
- id: CHG-0003-01
  title: Report failed uninstall removals and check the provider CLI before installing
  depends_on: []
  complexity: normal
  review: [quality, conformance]
  scope: ["harness/src/litman_harness/installation.py", "harness/src/litman_harness/interfaces/cli.py", "harness/deployment/**", "harness/tests/**"]
  acceptance:
    AC-01: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/test_installation.py'"
    AC-02: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/test_installation.py tests/interfaces tests/deployment/test_install_script.py'"
    AC-03: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/deployment/test_install_script.py'"
    AC-06: "bash -lc 'cd core && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q && cd ../harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'"
- id: CHG-0003-02
  title: Replace both manual validation documents with one Windows Codex app guide
  depends_on: [CHG-0003-01]
  complexity: normal
  review: [conformance]
  scope: ["docs/**", "README.md", "core/README.md", "core/docs/**", "harness/docs/**", "harness/deployment/README.md"]
  acceptance:
    AC-04: "bash -lc 'test ! -e docs/validacion_manual_instalacion.md && test ! -e docs/windows_manual.md && test -f docs/windows-codex-validation.md && ! grep -rIl --exclude-dir=.factory --exclude-dir=dist --exclude-dir=.git -e validacion_manual_instalacion -e windows_manual .'"
    AC-05: manual
```

## Risks and open questions
- Some Codex app outputs on Windows (UI text, real install paths, whether the app puts `codex` on
  `PATH`, `irm | iex` behaviour on `exit`) cannot be derived from the code; the guide marks them
  "observe and record". The first real run may need small guide corrections.
- CHG-0003-02 depends on CHG-0002 being merged first (see Implementation notes); the Factory cannot
  express a cross-change dependency, so the lead agent must check it.
- Discard with a locked file returns a generic `internal_error`; the guide records it as a known
  limitation. Improving that message would be a separate change.
