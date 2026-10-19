# Harness development

This page is the stable entry point for contributors to `litman-harness`, a
Python 3.11 distribution that is independent from `litman-core`.

Follow the repository [agent instructions](../../AGENTS.md) and the narrower
[Harness instructions](../AGENTS.md) before making changes. The
[codebase map](../../docs/codebase-map.md) defines ownership across the two
packages.

## Local setup and checks

From the repository checkout:

```bash
cd harness
UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv sync
UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q
```

The root [agent instructions](../../AGENTS.md) are the authority for required
validation. The package's `pyproject.toml` and `uv.lock` own its development
dependencies; do not use Core's environment or lockfile.

## Documentation map

- [Architecture](architecture.md) owns package structure, the Drive dossier
  model, the Core process boundary, publication, summaries, and product-agent
  integration.
- [Operations](operations.md) owns configuration, authentication, operation
  semantics, concurrency, recovery, and pending authorized validation.
- [Decisions](decisions.md) records durable Harness choices and their rationale.
- [Installation](../deployment/README.md) owns guided end-user installation,
  maintenance, uninstallation, and advanced wheel installation.
- The repository [public Core CLI contract](../../docs/contracts.md) owns the
  exact versioned process interface used by Harness. Core's
  [internal run documentation](../../core/docs/contracts.md) explains Core's
  implementation but is not the interface Harness consumes.

## Change boundaries

Harness owns dossier management, personal OAuth-based Drive access, local plan
and operation state, publication into the connected dossier, and the `litman`
and `litman-mcp` interfaces. It must invoke `litman-core` as a process and must
not import Core modules.

Product-agent resources under `harness/agent/` are part of installed product
behavior, not contributor instructions. Repository development skills under
`.agents/` and `.claude/skills/` are a separate system. Do not change either
runtime prompts or product-agent resources unless the task explicitly includes
them.
