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
  [repository decisions](decisions/README.md) for cross-package architecture,
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
