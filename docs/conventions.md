# Repository conventions

The operational authority for agents, validation, scope, and the Software
Factory is [AGENTS.md](../AGENTS.md). This page records technical conventions;
it does not replace or repeat those instructions.

## Package boundaries

- Keep Core and Harness as separate Python distributions with independent
  project metadata, lockfiles, tests, and operations.
- Change their shared interface only through the versioned
  [public CLI contract](contracts.md). Harness runs `litman-core` as a process
  and must not import its modules.
- Keep repository development tooling at the root and product-agent resources
  in `harness/agent/`. See the [codebase map](codebase-map.md).
- Keep package-specific implementation decisions beside their owner. Reserve
  [repository decisions](decisions/index.md) for cross-package architecture,
  public contracts, security, data models, and durable development process.

## Implementation style

- Prefer deterministic code, explicit state transitions, and explicit
  preview/apply boundaries.
- Treat source code, schemas, project metadata, and executable configuration as
  evidence for technical documentation.
- Use existing package structure and vocabulary before introducing a new
  abstraction or term.

## Documentation

- Write maintained repository documentation in English. Preserve literal CLI
  values, identifiers, paths, configuration keys, and machine output.
- Give each topic one canonical owner. Entry points should summarize and link
  instead of copying complete procedures.
- Keep relative links valid and retain established entry-point paths when
  moving detailed content.

## Commits and branches

- Orca's base branch is `master`; Factory task workspaces use their task ID as
  the branch name.
- Keep commits coherent and review the full task diff before submission.

## Known pitfalls

- The root `.claude/` directory was ignored before Factory installation; only
  explicitly unignored Factory files are tracked. (2026-10-19, Factory
  initialization)
- Harness test directories have no `__init__.py` and pytest uses its default
  import mode, so two test modules with the same basename (for example
  `tests/adapters/test_documents.py` and `tests/dossier/test_documents.py`)
  fail collection; give each test module a unique name. (2026-10-19,
  CHG-0006-01)
- `openpyxl.load_workbook` rejects a path without an `.xlsx` extension, so
  downloaded workbooks must be saved as `file.xlsx`, not extensionless
  temporary files. (2026-10-20, CHG-0007-02)
- `action_id()` (`harness/src/litman_harness/dossier/service.py`) hashes only
  `kind`, `resource_id`, `parent_id` and `name`, never `metadata`. A plan whose
  actions can legitimately share all four (for example two operations of the
  same kind on the same file with identical content, as two `add` comments
  can be) collapses them onto the same `action_id`, so `OperationRun` treats
  the second action as already done and replays the first one's output,
  silently dropping it. When a new plan kind's actions are not already
  disambiguated by validation (as `file_changes`' per-destination
  `name_exists` check disambiguates renames and copies), give each action a
  plan-local nonce in one of those four hashed fields — `comment_changes`
  uses the action's index as `parent_id`, keeping the real target ID in
  `metadata`. (2026-10-20, CHG-0007-06, quality review)
- `swfactory task verify` runs each acceptance command without a shell, so a
  command such as `cd harness && uv run pytest …` is reported `not_run`
  (`No such file or directory: 'cd'`). Write acceptance commands the way
  `[checks]` does, for example `bash -lc 'cd harness && …'` or
  `uv --directory harness run pytest …`. (2026-10-21, CHG-10.1)
- `swfactory` treats every acceptance value other than `manual` as a command,
  so a prose criterion (CHG-10.2's AC-08, "Run the required full Harness and
  Core suites …") is executed, reported `not_run`, and cannot be recorded with
  `--manual` (`ac_not_manual`). Write a criterion verified by hand or by review
  as `manual`, and put the procedure in the design. (2026-10-21, CHG-10.2)
