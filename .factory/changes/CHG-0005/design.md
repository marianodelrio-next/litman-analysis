# CHG-0005 — Windows: run the Harness CLI via python -m and fit local original names to the path budget

## Context
A real Windows 11 test with the Codex app (user profile `Mariano del Río`)
completed the analysis end to end, but needed two manual workarounds.

1. **Installer and the `litman` launcher.**
   - `harness/deployment/install.ps1:61` builds the `litman` path from
     `uv tool dir --bin`. Windows PowerShell decodes captured native output
     with the console code page, but uv writes UTF-8, so the path came back
     as `Mariano del R├¡o` and the script tried to run a nonexistent file.
   - With the path corrected, Windows 11 Smart App Control blocked the
     uv-generated `litman.exe` (Code Integrity events 3118, 3077, 3033).
   - The person finished the install by running the tool environment's
     interpreter directly:
     `& "$env:APPDATA\uv\tools\litman-harness\Scripts\python.exe" -m litman_harness.interfaces.cli install --app codex --source "$env:LOCALAPPDATA\LitMan\src"`
     (result `ok: true`).
   - After that, `litman-mcp.exe` (MCP, `installation.py:170`) and
     `litman-core.exe` (`adapters/core.py:50`) ran without being blocked:
     context creation, analysis and filling all worked from the Codex app.
   - `harness/deployment/uninstall.ps1:15-17` has the same
     `uv tool dir --bin` + `litman.exe` pattern.
   - `litman.exe` is also what the product agent is told to run.
     `installation.py:169,228` renders `{{LITMAN_BIN}}` in
     `harness/agent/workspace/AGENTS.md:11` as `script_path("litman")`.
     The `preparar-equipo` skill uses that command for
     `litman install --oauth-client` and `litman login`
     (`agent/skills/preparar-equipo/SKILL.md:15,18`). It is unknown how the
     agent got past this on the test machine, so it is treated as blocked
     too.
   - Verified: `litman_harness/interfaces/cli.py:116` has an
     `if __name__ == "__main__"` guard, so `python -m litman_harness.interfaces.cli` works.

2. **Work path too long.**
   - On Windows, `harness/src/litman_harness/analysis/inputs.py:_download_targets`
     raises `work_path_too_long` when
     `len(str(target)) + CORE_PATH_MARGIN (60) > WINDOWS_PATH_LIMIT (260)`.
   - The target is
     `<work_root>\litman-analysis-XXXXXXXX\<operation_id>\<local_name>`
     (`analysis/service.py:146,213`), where `operation_id` is a 36-character
     UUID and the default `work_root` is
     `%LOCALAPPDATA%\litman-harness\work` (`local_paths.py:36-38,60`).
   - With a typical profile, the input directory alone is about 120
     characters. `_windows_local_name` allows a local name of up to
     `WINDOWS_COMPONENT_LIMIT = 120` characters (`<file_id>-<stem><.ext>`,
     where a real Drive `file_id` is about 33 characters).
   - So any Drive name longer than about 45 characters fails with the
     default configuration. The person got past it by pointing
     `LITMAN_HARNESS_WORK_DIR` at a shorter temporary directory.
   - Core copies the originals to
     `%TEMP%\litman-core\<job_id>-XXXXXXXX\case\<local_name>`
     (`core/.../storage/local.py:19`, `core/.../config.py:_default_workspace`).
     With the default `%TEMP%` and `LITMAN_CORE_WORKSPACE_DIR` unset, that
     prefix (about 106 characters) is shorter than the Harness input
     directory.
   - Core's derived files (`doc_<12 hex>.md`, `pipelines/runner.py`,
     `documents/normalize.py:38`) do not reuse the original name. So the
     Harness input path is the binding constraint, and `CORE_PATH_MARGIN`
     stays as the allowance for what Core creates. A custom, deeper
     `LITMAN_CORE_WORKSPACE_DIR` is not covered; the Harness never sets it.

## Goal and scope
In scope:
- `install.ps1` and `uninstall.ps1` read uv's output as UTF-8 and run the
  Harness CLI through the tool environment's
  `python.exe -m litman_harness.interfaces.cli`, never through `litman.exe`.
- On Windows, the `litman` command rendered into the workspace `AGENTS.md`
  uses the same `python.exe -m` form. On POSIX it is unchanged.
- On Windows, local original names are shortened to fit the path budget left
  by the actual input directory, so the default work root works with long
  Drive names.
- Tests and the affected documentation.

Out of scope:
- The MCP command (`litman-mcp.exe`) and Core invocation (`litman-core.exe`):
  the real test showed they were not blocked.
- `install.sh` and `uninstall.sh`.
- POSIX local names.
- The default work root location.
- `operation_id` and `publication_id` formats.
- Product skills text.
- Core.

## Acceptance criteria
- AC-01: Given `install.ps1` and `uninstall.ps1`, when inspected, then
  neither contains `litman.exe` and both invoke
  `& $Python -m litman_harness.interfaces.cli` (`install --app … --source …`
  and `uninstall @UninstallArgs` respectively). `$Python` is
  `Join-Path <uv tool dir> 'litman-harness\Scripts\python.exe'` —
  verified by: static tests in `harness/tests/deployment/test_install_script.py`.
- AC-02: Given each script, when inspected, then `[Console]::OutputEncoding`
  is saved, set to `[System.Text.Encoding]::UTF8` before `uv tool dir` is
  captured, and restored in a `finally` block around that capture. The `try`
  contains only the capture. When `pwsh` is available, both scripts parse
  without errors. Real decoding is proven only by AC-10 — verified by: static
  test plus the existing pwsh parse test (skipped without pwsh).
- AC-03: Given each script, when inspected, then:
  - in `install.ps1`, a `Test-Path $Python` check comes before
    `& $Python`, and its failure branch writes a Spanish message containing
    the path and runs `exit 1`;
  - `uninstall.ps1` keeps the `if (Test-Path …)` guard that skips the CLI
    uninstall when the interpreter is absent;
  - `test_uninstall_ps1_checks_lastexitcode_after_litman_uninstall` keeps its
    name and is retargeted to the new `& $Python -m … uninstall` line —
    verified by: static tests.
- AC-04: Given Windows (simulated with `platform.system`), when
  `litman install` renders the workspace `AGENTS.md`, then the `litman`
  command is `& "<scripts dir>\python.exe" -m litman_harness.interfaces.cli`.
  `<scripts dir>` is `sysconfig.get_path("scripts")`, the folder that
  `script_path` uses. Given POSIX, it is still `script_path("litman")` —
  verified by: unit tests in `harness/tests/test_installation.py`.
- AC-05: Given Windows (simulated) and an input directory built as
  `tmp_path / ("x" * (120 - len(str(tmp_path)) - 1))` (asserted to be 120
  characters), when a Drive original with a 33-character `file_id` and a name
  of 200 characters plus `.pdf` is downloaded, then:
  - the download succeeds;
  - the local name starts with `<file_id>-`, ends with `.pdf`, and has no
    invalid Windows characters or trailing dot or space;
  - `len(str(target)) + CORE_PATH_MARGIN <= WINDOWS_PATH_LIMIT`;
  - the snapshot `name` is the untouched Drive name.

  Verified by: unit test in `harness/tests/analysis/test_inputs.py`.
- AC-06: Given Windows and a Drive name whose apparent suffix after the last
  dot is longer than `MAX_EXTENSION = 10` characters (for example
  `informe.final-version-revisada-definitiva`), then the whole name is
  treated as the stem (no extension) and shortened like any other.
  `work_path_too_long` is not raised with the default-length directory from
  AC-05 — verified by: unit test.
- AC-07: Given an input directory so deep that not even `<file_id>-` + one
  stem character + extension fits within the budget, when downloading, then
  `work_path_too_long` is raised before any download — verified by: the
  existing test `test_windows_rejects_deep_workspace_before_downloading`
  (kept, adjusted only if its path no longer meets that condition).
- AC-08: Given two originals whose shortened names would match
  case-insensitively, then `local_name_collision` is still raised. Given
  POSIX, local names are unchanged — verified by: existing and new unit tests
  in `harness/tests/analysis/test_inputs.py`.
- AC-09: Given the docs, then they describe the new behaviour without
  recommending `LongPathsEnabled` or disabling Smart App Control (verified by
  manual review). Each task owns the sections listed below.
  - **Task 01:**
    - `harness/deployment/README.md`: the install/uninstall description
      around lines 39-45 now runs the CLI via `python.exe -m` on Windows,
      because Smart App Control may block uv launchers. Profiles with
      accents are supported.
    - `docs/windows-codex-validation.md`: the install and uninstall checks
      (around lines 30, 79 and 281-292).
    - `docs/guia-litman-windows.md`: the install step (around line 62),
      plus a troubleshooting row for Smart App Control.
  - **Task 02:**
    - `harness/docs/operations.md:93-95`
    - `docs/windows-codex-validation.md:230-236`
    - `docs/guia-litman-windows.md:156`

    These now say that long Drive names are shortened locally and that
    `work_path_too_long` only applies to a very deep
    `LITMAN_HARNESS_WORK_DIR`.
- AC-10: Manual check on a real Windows 11 machine whose profile contains
  `í`, with Smart App Control on. Verified by: manual step by the person,
  recorded as pending if not done before closing.
  - **Task 01:** reinstall with the one-liner, run "prepara mi equipo"
    (including `litman install --oauth-client` and `litman login` through
    the rendered command), then uninstall.
  - **Task 02:** with `LITMAN_HARNESS_WORK_DIR` unset, analyse a dossier
    containing an original whose name exceeds 100 characters.
- AC-11: The full `harness/` suite passes — verified by:
  `UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q` from `harness/`.

## Approach
**Installer and the `litman` command.**

In both scripts:
1. Save `[Console]::OutputEncoding`.
2. Set it to `[System.Text.Encoding]::UTF8`.
3. Capture `uv tool dir`, which is the tools root, not `--bin`, so it honours
   `UV_TOOL_DIR`.
4. Restore the original encoding in `finally`.
5. Build `$Python = Join-Path $ToolDir 'litman-harness\Scripts\python.exe'`.
6. Invoke `& $Python -m litman_harness.interfaces.cli …` and check
   `$LASTEXITCODE` as today.

If setting `[Console]::OutputEncoding` throws because there is no console,
catch it, leave the encoding as it is and continue; a non-ASCII path may then
still fail. This matches the workaround that worked on the real machine.

In `installation.py`, on Windows, `{{LITMAN_BIN}}` becomes
`& "<python.exe>" -m litman_harness.interfaces.cli`. The leading `&` is the
PowerShell call operator, which the Codex and Claude shells on Windows need.
The MCP registration keeps `litman-mcp.exe`.

Rejected alternatives:
- Hardcoding `$env:APPDATA\uv\tools`: it ignores `UV_TOOL_DIR`.
- Keeping `litman.exe`: Smart App Control blocked it.
- Asking users to disable Smart App Control: unacceptable.
- Code-signing: we do not build uv's launchers.
- Switching MCP and Core to `python -m` as well: the test shows it is not
  needed, so it is left out to keep the change small.

**Local names.**
1. Give `_windows_local_name` a `limit` parameter (default
   `WINDOWS_COMPONENT_LIMIT`).
2. A suffix longer than `MAX_EXTENSION = 10` characters is treated as part
   of the stem.
3. In `_download_targets` on Windows, compute
   `budget = WINDOWS_PATH_LIMIT - CORE_PATH_MARGIN - len(str(inputs_dir)) - 1`
   (the separator) and use `min(WINDOWS_COMPONENT_LIMIT, budget)`.
4. The `<file_id>-` prefix and the extension are always kept; only the stem
   is truncated, as today.
5. If the budget cannot hold the prefix, one stem character and the
   extension, raise `work_path_too_long` with the existing message.
6. Collision detection runs on the final names. The existing length check
   stays as a final assertion.

Rejected alternatives:
- `LongPathsEnabled`: it needs admin rights and possibly a reboot, every
  executable in the chain (Codex, document converters) must be long-path
  aware, and it contradicts `harness/docs/operations.md`.
- `\\?\` paths: the paths also reach subprocesses, libraries and the LLM
  prompt.
- A shorter default work root: it gains only about 30 characters, still
  fails with long names, and moves every user's data.
- A shorter `operation_id` directory: it becomes Core's `job_id` and the
  published `publication_id`, which would be a product change.

No ADR needed; the existing "no `LongPathsEnabled` dependency" position is kept.

## Implementation notes
- `harness/deployment/install.ps1`: replace lines 61-63. Messages and
  comments are in Spanish without accents, as in the rest of the file.
- `harness/deployment/uninstall.ps1`: replace lines 15-19 with the same
  pattern, keeping the `Test-Path` skip, the `$LASTEXITCODE` check and
  `uv tool uninstall`.
- `harness/tests/deployment/test_install_script.py`: follow the existing
  static PS1 tests (`test_install_ps1_checks_provider_cli_before_clone_and_tool_install`,
  around line 205) and keep the provider-CLI-before-clone ordering
  assertions valid.
- `harness/src/litman_harness/installation.py:169,228`: add a small helper
  (in `installation.py`, or in `adapters/core.py` next to `script_path`) that
  returns the rendered command per platform. Patch `platform.system` in the
  module that owns the helper. See `tests/test_installation.py:59` for how
  the rendered `AGENTS.md` is read.
- `harness/src/litman_harness/analysis/inputs.py`: `_windows_local_name`,
  `local_original_name` (it may gain an optional `limit`; POSIX ignores it)
  and `_download_targets`. Lengths are characters, `len(str(path))`, as
  today.
- `harness/tests/analysis/test_inputs.py`: use the existing pattern
  `monkeypatch.setattr(inputs.platform, "system", lambda: "Windows")`. The
  `_plan` and `Drive` helpers use ids like `id0`, so add a way to use a
  33-character id (for example a parameter, or a local plan and fake file
  in the new test).
- Task 02 depends on task 01 only because both edit
  `docs/guia-litman-windows.md` and `docs/windows-codex-validation.md`, in
  the separate sections listed in AC-09.

## Tasks
```yaml
- id: CHG-0005-01
  title: Run the Harness CLI on Windows via python -m (installer scripts and rendered litman command)
  depends_on: []
  complexity: normal
  review: [quality, conformance]
  scope: ["harness/deployment/**", "harness/tests/deployment/**", "harness/src/litman_harness/installation.py", "harness/src/litman_harness/adapters/core.py", "harness/tests/test_installation.py", "harness/tests/adapters/**", "docs/guia-litman-windows.md", "docs/windows-codex-validation.md"]
  acceptance:
    AC-01: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/deployment/test_install_script.py'"
    AC-02: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/deployment/test_install_script.py'"
    AC-03: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/deployment/test_install_script.py'"
    AC-04: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/test_installation.py'"
    AC-09: manual
    AC-10: manual
    AC-11: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'"
- id: CHG-0005-02
  title: Shorten Windows local original names to fit the actual input path budget
  depends_on: [CHG-0005-01]
  complexity: normal
  review: [quality, conformance]
  scope: ["harness/src/litman_harness/analysis/inputs.py", "harness/tests/analysis/**", "harness/docs/operations.md", "docs/guia-litman-windows.md", "docs/windows-codex-validation.md"]
  acceptance:
    AC-05: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/analysis/test_inputs.py'"
    AC-06: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/analysis/test_inputs.py'"
    AC-07: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/analysis/test_inputs.py'"
    AC-08: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/analysis/test_inputs.py'"
    AC-09: manual
    AC-10: manual
    AC-11: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'"
```

## Risks and open questions
- CI cannot reproduce Smart App Control, an OEM-code-page console or real
  Windows path limits; AC-10 is the only real proof.
- If Smart App Control later also blocked the tool's `python.exe`,
  `litman-mcp.exe` or `litman-core.exe`, the out-of-scope MCP and Core
  commands would need the same `python -m` treatment.
- Shortened local names only make long document names less readable inside
  the local workspace; the Drive name stays in `input_snapshot.name`.
- A deeper custom `LITMAN_CORE_WORKSPACE_DIR` is outside the
  `CORE_PATH_MARGIN` reasoning.
