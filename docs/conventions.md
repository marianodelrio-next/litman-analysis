# Conventions

## Code

- Keep Core and Harness as separate distributions. Changes to their interface go through the [versioned CLI contract](contracts.md); Harness calls `litman-core` as a process.
- Keep development agent configuration in the repository root and product agent resources in `harness/agent/`. See the [codebase map](codebase-map.md).
- Preserve the existing deterministic processing and explicit preview/apply boundaries documented in [Core decisions](../core/docs/decisions.md) and [Harness development](../harness/docs/development.md).

## Tests

- Run `UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q` in each changed distribution (`core/` or `harness/`). The Factory test check runs both.
- When Core Docker deployment changes, also validate the Compose file and build the image as specified in [AGENTS.md](../AGENTS.md).
- The Factory build check builds both Python distributions. No lint or static typecheck tool is configured yet.

## Commits and branches

- Orca's base branch is `master`. Factory approvals are committed on that branch; task workspaces start from it. See [AGENTS.md](../AGENTS.md) and `/factory-design` for the approval flow.
- Review the diff before committing. Factory initialization leaves changes uncommitted.

## Known pitfalls

- The root `.claude/` directory was ignored before Factory installation; only Factory skills and approval settings are explicitly unignored. (2026-10-19, Factory initialization)
