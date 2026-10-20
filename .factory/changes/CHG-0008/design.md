# CHG-0008 — Tagged releases, changelog and the actualizar-equipo update skill

## Context
Verified current behaviour:

- Users install and update with the guided one-liner (`harness/deployment/README.md:27-41`). The
  scripts `harness/deployment/install.sh:48-59` and `install.ps1:43-56` fetch tags into a hidden
  checkout, check out the newest `v*` tag (`git tag -l 'v*' --sort=-v:refname`) and fall back to
  `origin/HEAD` when no tag exists. Then they run `uv tool install --force --python 3.11 <src>/harness
  --with <src>/core` and `litman install --app <app> --source <src>`.
- No `v*` tag exists, so every update installs whatever is on `master`.
- The version `0.1.0` is written by hand in `core/pyproject.toml:7`, `core/src/litman_core/__init__.py:5`,
  `harness/pyproject.toml:7`, the pin `litman-core==0.1.0` in `harness/pyproject.toml:11`,
  `harness/src/litman_harness/__init__.py:9`, the local package entries of `core/uv.lock` and
  `harness/uv.lock`, and in documentation examples: `docs/contracts.md:100` and `:132`,
  `docs/windows-codex-validation.md:135`, `harness/deployment/README.md:128`,
  `core/deployment/local-install/README.md:17`. It has never been bumped. There is no changelog.
- `installation.install()` (`harness/src/litman_harness/installation.py:147`) copies the skills
  listed in `SKILL_NAMES` (`installation.py:28`), records a manifest without the installed version
  or the source path, and never runs Git or uv. `status()` feeds `diagnose`
  (`harness/src/litman_harness/interfaces/assembly.py:127-157`), which reports the Core version but
  not the Harness version.
- CLI-only operations (`login`, `install`, `uninstall`) are dispatched in
  `harness/src/litman_harness/interfaces/cli.py:80-100` and are absent from MCP `tools/list`.
- The product skill `harness/agent/skills/preparar-equipo/SKILL.md` has an "Actualizar" section
  that only asks the person to paste the install command again.
- Verified in this session: `uv tool install --force` of a local directory reinstalls changed
  code even when the version is unchanged. `git checkout` replaces files with a new inode, so a
  running `install.sh` is not corrupted when the checkout moves. `git tag --sort=-v:refname` orders
  `v0.10.0` above `v0.9.0` but puts `v1.0.0-rc1` above `v1.0.0`. After a published tag is moved,
  `git fetch --tags` in an existing clone exits 1.

## Goal and scope
LitMan is published as a single product version `X.Y.Z`, shared by both packages, through
annotated `vX.Y.Z` tags. Users only ever install the newest tag. A root `CHANGELOG.md` records the
changes of every version. A scripted release flow keeps every version site consistent and is
documented so that an agent can cut a release when the person asks. The new product skill
`actualizar-equipo` checks for a newer version, summarizes its changelog in brief non-technical
Spanish, runs or explains the update, and tells the person to restart the app.

In scope: `CHANGELOG.md`, `scripts/release.py` and its tests, release documentation and an
`AGENTS.md` section, an ADR, tag-only installers, a CLI-only `litman check-update`, the Harness
version in `diagnose`, the source path in the install manifest, the new skill and the related
skill, workspace and documentation updates.

Out of scope: GitHub Releases, CI, pre-release tags, removing skills that a later version
deletes or renames, migrations of local settings or state, and actually publishing `v0.1.0`.
Publishing is the person's action after this change is merged (see Risks).

Policies agreed with the person: tags are never test or pre-release tags, a published tag is never
moved or deleted, and a bad release is fixed by publishing the next version.

## Acceptance criteria
- AC-01: Given the repository, when `python3 scripts/release.py check` runs, then it exits 0 only
  if every version site in the script's explicit list (the packages, the `litman-core==` pin, both
  lockfiles' local package entries and the documentation examples listed in Context, except the
  historical `docs/windows-codex-validation.md`, which gets an `X.Y.Z` placeholder) holds the
  same `X.Y.Z` and `CHANGELOG.md` parses (an `## [Unreleased]` section followed by
  `## [X.Y.Z] - YYYY-MM-DD` sections in descending order). A changelog with only `[Unreleased]`
  and no version section is valid for `check`, which is the real state before the first release.
  It names each mismatched file otherwise. The real repository passes. Verified by: `harness/tests/deployment/test_release.py` (temporary
  fixture repositories and the real repository).
- AC-02: Given a clean tree, when `release.py prepare X.Y.Z [--date YYYY-MM-DD] [--no-tests]` runs,
  then it rewrites every version site to `X.Y.Z` and moves the `[Unreleased]` entries to a new
  `## [X.Y.Z] - <date>` section, leaving an empty `[Unreleased]`. Unless `--no-tests` is given, it
  then runs both test suites. It refuses, without changing any file, a version that does not match
  `^\d+\.\d+\.\d+$`, a version not greater than the newest `vX.Y.Z` tag or lower than the current
  version, an empty `[Unreleased]` section, and a dirty tree. It never commits, tags or pushes.
  Verified by: `test_release.py`.
- AC-03: Given `release.py tag [--push]`, when the branch is not `master`, the tree is dirty, `HEAD`
  differs from `origin/master` after `git fetch origin`, `check` fails, the changelog has no
  version section or its newest one differs from the version, or `vX.Y.Z` already exists locally or on `origin`, then it
  refuses without creating a tag. Otherwise it creates the annotated tag `vX.Y.Z` on `HEAD` and
  prints the push command. Only with `--push` does it run `git push origin vX.Y.Z`. Verified by:
  `test_release.py` with a local bare repository as `origin`.
- AC-04: Given an agent asked to "release" or "publish version X.Y.Z", when it reads `AGENTS.md`, then a
  short "Releases" section tells it to follow `docs/releasing.md`. That page describes the full
  flow (prepare on a branch, pull request, merge, `tag --push` on `master`, announce) and the tag
  policies. `AGENTS.md` also requires user-visible changes to add an entry under `## [Unreleased]`.
  `CHANGELOG.md` exists with an `[Unreleased]` section describing LitMan's current user-visible
  capabilities for the first release. An ADR records the release policy, and `docs/index.md` plus
  `docs/codebase-map.md` list the new files. Verified by: manual documentation review.
- AC-05: Given the install scripts, when the hidden checkout has no `vX.Y.Z` tag, then they stop
  with a Spanish message saying no published version exists and install nothing. When tags exist,
  they check out the newest one and never fall back to a branch. Tags not matching
  `^v\d+\.\d+\.\d+$` are ignored (with `v0.9.0`, `v0.10.0`, `v1.0.0-rc1` and `vfoo`, the result is
  `v0.10.0`). Verified by: `harness/tests/deployment/test_install_script.py`. It uses local
  repositories through `LITMAN_REPO` / `LITMAN_SRC_DIR` and, for the no-tag and tag-selection
  cases, a fake `uv` that logs its calls, so no network is needed. Network-dependent end-to-end
  steps are skipped as today. A text test covers `install.ps1`.
- AC-06: Given an installation, when `litman check-update` runs, then it prints
  `{"ok": true, "result": {...}}` with these fields:
  - `installed`: the running `__version__`, a string.
  - `latest`: the newest `vX.Y.Z` tag after `git fetch --tags` in the recorded source checkout,
    without the `v`, or `null` if no tag exists.
  - `update_available`: true only if `latest` is greater than `installed`. It is false when no
    tag exists or when the installed version is newer (a development install).
  - `changes`: a list, oldest first, of `{"version": "X.Y.Z", "date": "YYYY-MM-DD", "text": "<the
    section's Markdown body>"}` for the sections with installed < version ≤ latest, read from
    `git show v<latest>:CHANGELOG.md`. It is empty when no update is available.
  - `command`: the update command for this platform and app, or `null` when no update is
    available.

  Non-Windows platforms (Linux, Darwin) get the POSIX command. Without a recorded source it
  returns `update_source_missing`. Git missing or a failing Git call returns
  `update_check_failed`. `check-update` and `check_update` are absent from `registry()` and MCP
  `tools/list`, and `cli.main(["check-update"])` dispatches to it. Verified by:
  `harness/tests/test_updates.py` (injected runner and `which`), plus new assertions in
  `harness/tests/interfaces/test_transports.py`.
- AC-07: Given `litman install`, then the manifest records the resolved source path, and
  `diagnose` reports the installed Harness version without exposing any local path. Verified by:
  `harness/tests/test_installation.py` and the diagnose tests.
- AC-08: Given the product resources, then `actualizar-equipo` is installed, recorded in the
  manifest and uninstalled like the other skills. `preparar-equipo` no longer handles updates:
  no "Actualizar" section, and no update wording in its description or body (today lines 3, 7
  and 38). `ayuda-litman` and the workspace `AGENTS.md` mention "actualiza mi equipo". The new
  skill has frontmatter `name: actualizar-equipo`, mentions `litman check-update` and `command`,
  handles `update_source_missing` and `update_check_failed`, and ends with the restart
  instruction. Verified by: `test_installation.py`, assertions in
  `harness/tests/interfaces/test_agent_files.py`, and a manual review that the skill follows the
  flow in Approach.
- AC-09: Given the user documentation, then `harness/deployment/README.md`,
  `docs/guia-litman-windows.md`, `docs/windows-codex-validation.md`, `harness/docs/architecture.md`
  and `harness/docs/operations.md` describe tag-only installation, `actualizar-equipo`, the
  restart, and the one-time manual reinstall for existing installations. Verified by: manual
  documentation review.
- AC-10: Both suites pass: `UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q` from `core/` and
  from `harness/`. Verified by: command.

## Approach
**One product version.** The tag `vX.Y.Z` is the LitMan version. Both packages, the Harness pin on
Core, both lockfiles and the documentation examples carry the same `X.Y.Z`. `scripts/release.py`
owns the explicit list of version sites, so `check`, `prepare` and its tests agree on one source.
The alternative of independent package versions was rejected: users see one product, and the
changelog and tag map one to one.

**Changelog.** The root `CHANGELOG.md` follows Keep a Changelog 1.1.0 (`## [Unreleased]`, then
`## [X.Y.Z] - YYYY-MM-DD` with `### Added` / `### Changed` / `### Fixed` subsections). It is in
English, like everything published. Entries describe user-visible behaviour in plain language, so
the skill can summarize them in Spanish. The "NOVEDADES" file in Spanish was rejected by the
person.

**Release script.** `scripts/release.py` uses only the standard library and Python ≥ 3.11 and runs
with `python3` from the repository root. It has three subcommands: `check`, `prepare` and `tag`.
Two steps (`prepare` on a branch, then `tag` on `master` after the merge) fit the existing
pull-request workflow, so the release commit is reviewed like any other. The script never commits
or opens pull requests; the agent does that with normal Git and `gh`. It pushes only the tag, and
only with `--push`. Lockfile versions are rewritten textually, only in the `[[package]]` entries
named `litman-core` / `litman-harness`, so no network is needed. `docs/releasing.md` tells the
agent to confirm them with `uv lock --check` in `core/` and `harness/`.

**Tag-only installers.** The `origin/HEAD` fallback is removed, so a missing tag is an error.
Branches are never installed. The bootstrap one-liner still downloads `install.sh` /
`install.ps1` from `master` on raw.githubusercontent (there is no stable URL for "the newest tag"
without GitHub Releases), but the code it installs always comes from the tag.

**Update check.** A new module `harness/src/litman_harness/updates.py` holds the deterministic
logic and is exposed as the CLI-only `litman check-update`. It is not added to MCP, because
updating is a local machine operation like `install`. The installed version is the running
`litman_harness.__version__`, so no Git state is needed for it. The source path comes from the
manifest, written by `install()`. Its `command` runs the local install script of the source
checkout, and passes `LITMAN_SRC_DIR` so a custom checkout location is kept:
- POSIX: `LITMAN_APP=<app> LITMAN_SRC_DIR="<src>" sh "<src>/harness/deployment/install.sh"`.
- Windows: `$env:LITMAN_APP='<app>'; $env:LITMAN_SRC_DIR='<src>'; powershell -NoProfile
  -ExecutionPolicy Bypass -File "<src>\harness\deployment\install.ps1"`.

The script fetches again and moves to the newest tag. That run uses the installer of the
currently installed tag; installer changes take effect from the following update. The rejected alternative was a
`litman update` that reinstalls from Python, because the running process would replace its own
uv tool environment, which is the worst case on Windows.

**Skill `actualizar-equipo`** (Spanish, like the other product skills):
1. Run `litman check-update`. If there is no update, say LitMan is up to date and stop.
   - On `update_source_missing` (every installation made before this change), ask the person to
     paste the install command from the README once, then restart the app.
   - On `update_check_failed`, say in one business sentence that the new version could not be
     checked (for example, no connection or the app blocked it), and suggest retrying or
     contacting the developer.
2. Otherwise, give a brief non-technical Spanish summary of `changes`, at most a few sentences
   and never file names or technical terms.
3. On Linux, run `command`. On failure, explain in one business sentence and suggest repeating or
   contacting the developer.
4. On Windows, do not run it. Ask the person to close the app, paste `command` into PowerShell and
   reopen the app. Running processes such as `litman-mcp.exe` would likely block the reinstall.
5. Always finish by asking the person to close and reopen the app.

The person launches the skill when the developer announces a release. The "Actualizar" section
moves out of `preparar-equipo`.

**ADR.** Add `docs/decisions/0002-tagged-releases.md` (single version, tag-only installs, immutable
tags, changelog policy) and list it in `docs/decisions/README.md`.

## Implementation notes
- **Version sites** in `scripts/release.py` are a list of (path, regex) entries:
  - `core/pyproject.toml` and `harness/pyproject.toml` (`^version = "…"` in `[project]`);
  - `harness/pyproject.toml` (`"litman-core==…"`);
  - both `__init__.py` (`__version__ = "…"`);
  - the lockfile entries (`name = "litman-core"` / `name = "litman-harness"` followed by
    `version = "…"`);
  - the documentation examples listed in Context.

  `check` reports every mismatch, not only the first. Keep the list explicit, with no repo-wide
  search and replace.
- **Version comparison** uses tuples of ints. Tags that do not match `^v\d+\.\d+\.\d+$` are
  ignored by `release.py`, by `updates.py` and, through a glob plus filter, by the install
  scripts. In `install.sh`, filter with `grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$'` before `head -n1`; in
  `install.ps1`, use `Where-Object { $_ -match '^v\d+\.\d+\.\d+$' }`.
- **`prepare` and the first release:** the current version is already `0.1.0` with no tag. A
  target equal to the current version is allowed when no tag for it exists, so the first release
  is `prepare 0.1.0`.
- **`prepare` tests:** unless `--no-tests` is given, it runs `uv lock --check` and then
  `uv run --locked pytest -q` in `core/` and `harness/`, with
  `UV_CACHE_DIR=/tmp/licitaBot-uv-cache`. Plain `uv run` would re-lock silently and hide a broken
  textual lockfile rewrite.
- **Historical records:** `docs/windows-codex-validation.md:135` is the expected output of a
  recorded validation. Replace its version with the placeholder `X.Y.Z` instead of adding it to
  the version-site list. Tests of the script always
  pass `--no-tests` and `--date`.
- **`tag` checks** use `git rev-parse --abbrev-ref HEAD`, `git status --porcelain`,
  `git fetch origin`, `git rev-parse HEAD origin/master` and `git ls-remote --tags origin vX.Y.Z`.
  The annotated tag message is `LitMan X.Y.Z`.
- **Release tests** live in `harness/tests/deployment/test_release.py`, following the precedent of
  `test_install_script.py`, which already uses `REPO_ROOT = Path(__file__).parents[3]`.
- **Existing install test:** `test_install_script.py`'s fixture `committed_repo_copy` (around
  lines 74-93) commits without a tag. CHG-0008-02 must tag that commit `v<__version__>`, or
  `test_install_sh_end_to_end_then_idempotent_then_uninstall` breaks. The new no-tag and
  tag-selection tests follow `test_without_provider_cli_stops_before_cloning_or_installing`,
  which uses a fake binary on `PATH`. Build small
  fixture repositories in `tmp_path` that contain only the listed version sites (copied from the
  real repository) and a `CHANGELOG.md`. Run the script with `sys.executable`.
- **Install manifest:** in `installation.install()`, add `"source": str(source.resolve())` to
  `new_manifest`. Do not expose it in `status()`, because `diagnose` never shows paths. Add the
  top-level `"version": __version__` to `diagnose()` in `interfaces/assembly.py`.
- **`updates.py`:** take `env`, a `Runner` (see `adapters/core.py`, default `subprocess.run`), a
  `which` (default `shutil.which`) and the platform, so tests inject them. If Git is missing,
  return `update_check_failed`. Read all Git output (tags, `git show`) as UTF-8 explicitly
  (`encoding="utf-8"`); otherwise Windows decodes with the console code page and breaks
  non-ASCII text, which is the same reason `install.ps1` forces UTF-8. Document the top-level
  `version` of `diagnose` next to the existing diagnose description in
  `harness/docs/operations.md`, and add `updates.py` to the Harness rows of
  `docs/codebase-map.md`. Harness error codes are free strings passed to `HarnessError`
  (`harness/src/litman_harness/errors.py`; there is no central list). Raise the new codes the
  way `installation.py` raises `install_conflict`, and document them in `harness/docs/operations.md`.
- **CLI dispatch:** add the `check-update` branch in `interfaces/cli.py` beside `install` /
  `uninstall`, and mention it in the module docstring and the parser description. The workspace
  template already provides the right `litman` command per platform (`{{LITMAN_BIN}}`).
- **Changelog parsing** is shared logic: `release.py` cannot import the Harness, and the Harness
  never imports repository scripts. Implement a small parser in each, as a deliberate duplicate,
  and test both against the same fixture text.
- **Skill wiring:** add `actualizar-equipo` to `SKILL_NAMES`. `test_installation.py` iterates
  `SKILL_NAMES`; extend the help and skill coverage tests in `test_agent_files.py` if they assert
  the skill set.
- **Pitfalls:**
  - Never call real `git push` or the network in tests; use a local bare repository as `origin`.
  - On Windows, a local `.ps1` is blocked by the default execution policy, which is why the
    command uses `-ExecutionPolicy Bypass -File`.
  - The `CHANGELOG.md` `[Unreleased]` entries for this change itself must be user-visible
    descriptions, not implementation details.
  - `resumir-licitacion` is triggered by "actualiza el resumen de la licitación…"
    (`docs/guia-litman-windows.md:137`). The new skill's description must be narrow ("actualiza
    mi equipo", "actualiza LitMan", "hay una versión nueva"), never a bare "actualiza".

## Tasks
Dependencies: CHG-0008-02 parses the changelog format that CHG-0008-01 defines. CHG-0008-03 uses
`check-update` from CHG-0008-02.

```yaml
- id: CHG-0008-01
  title: Single product version, CHANGELOG.md and the scripted, documented release flow
  depends_on: []
  complexity: normal
  review: [quality, conformance]
  scope: ["scripts/**", "CHANGELOG.md", "AGENTS.md", "docs/**", "core/pyproject.toml", "core/uv.lock", "core/src/litman_core/__init__.py", "core/deployment/local-install/README.md", "harness/pyproject.toml", "harness/uv.lock", "harness/src/litman_harness/__init__.py", "harness/deployment/README.md", "harness/tests/deployment/test_release.py"]
  acceptance:
    AC-01: "bash -lc 'python3 scripts/release.py check && cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/deployment/test_release.py'"
    AC-02: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/deployment/test_release.py'"
    AC-03: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/deployment/test_release.py'"
    AC-04: manual
    AC-10: "bash -lc 'cd core && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q && cd ../harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'"
- id: CHG-0008-02
  title: Tag-only installers, the CLI-only check-update command and the installed version in diagnose
  depends_on: [CHG-0008-01]
  complexity: normal
  review: [quality, conformance]
  scope: ["harness/deployment/**", "harness/src/litman_harness/**", "harness/tests/**", "harness/docs/**", "docs/windows-codex-validation.md", "docs/codebase-map.md", "CHANGELOG.md"]
  acceptance:
    AC-05: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/deployment/test_install_script.py'"
    AC-06: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/test_updates.py tests/interfaces/test_transports.py'"
    AC-07: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/test_installation.py tests/interfaces'"
    AC-10: "bash -lc 'cd core && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q && cd ../harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'"
- id: CHG-0008-03
  title: The actualizar-equipo product skill and the update documentation
  depends_on: [CHG-0008-02]
  complexity: normal
  review: [quality, conformance]
  scope: ["harness/agent/**", "harness/src/litman_harness/installation.py", "harness/tests/**", "harness/docs/**", "harness/deployment/README.md", "docs/guia-litman-windows.md", "docs/windows-codex-validation.md", "CHANGELOG.md"]
  acceptance:
    AC-08: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/test_installation.py tests/interfaces/test_agent_files.py'"
    AC-09: manual
    AC-10: "bash -lc 'cd core && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q && cd ../harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'"
```

## Risks and open questions
- **Install gap between merge and the first tag.** Once CHG-0008-02 is merged, the one-liner from
  `master` refuses to install until `v0.1.0` exists. The person publishes `v0.1.0` right after
  CHG-0008-03 is merged, and nobody installs in between. `docs/releasing.md` states this.
- **First release and bootstrap.** After the three tasks are merged, the person asks an agent to
  release `0.1.0` (`prepare 0.1.0` on a branch, pull request, merge, `tag --push`). Existing
  installations run Harness `0.1.0` from an older `master` commit, so `check-update` would report
  them up to date. They must reinstall once with the one-liner after `v0.1.0` is published, to get
  the tagged code and the new skill. `docs/releasing.md` and the install README say so.
- **Installer compatibility in both directions.** The one-liner reads `install.sh` /
  `install.ps1` from `master`, so they must keep installing older tags. An update runs the
  installer of the currently installed tag, so it must be able to install newer tags; a breaking
  installer change needs a one-time manual reinstall. On Windows, it is not verified that
  `git checkout` can replace the running `install.ps1` (PowerShell parses the file before
  running it).
- **App permissions.** Not verified: on Ubuntu, Codex or Claude may require approval, or the Codex
  sandbox may block network and writes outside the workspace when the skill runs `command`. If it
  is blocked, the skill should fall back to the Windows path (person runs the command). Manual
  validation is recorded in `docs/windows-codex-validation.md` and the Ubuntu notes.
- **Windows reinstall with the app closed** is assumed to work like today's manual update. It is
  not re-verified here.
- **Removed or renamed skills** stay on user machines after an update. This is out of scope and
  recorded for a later change.
