# Shared architecture

LitMan contains two independent Python 3.11 distributions and repository-level
development tooling. Each distribution owns its project metadata, lockfile,
environment, tests, operations, and internal decisions.

```text
Person or product agent
        |
        v
litman / litman-mcp  (Harness)
        |
        | child process: litman-core run --config
        v
litman-core          (Core)
```

## Package boundary

`litman-core` lives in `core/` and analyzes procurement material. Its only
public application entry point is the `litman-core` CLI. It can be installed
and run independently, with Docker available as an optional Core-only
deployment boundary.

`litman-harness` lives in `harness/` and exposes the `litman` and `litman-mcp`
interfaces. It manages a dossier with personal OAuth and declares Core as a
distribution dependency, but it does not import `litman_core`. For each
analysis it creates a minimal configuration, runs `litman-core run --config`,
and consumes the process result.

The versioned [public CLI contract](contracts.md) owns command behavior, public
configuration, exit behavior, and JSON schemas at this boundary. Core's
[internal run contract](../core/docs/contracts.md) owns workspace layout,
lineage, and internal publication details; those details are not a stable
interface for Harness or other consumers.

## Documentation and tooling boundary

The repository root owns the product overview, this cross-package architecture,
the public contract, the [codebase map](codebase-map.md), and development rules.
Package-specific architecture, operations, and decisions remain with their
owners:

- [Core documentation](../core/README.md)
- [Harness documentation](../harness/README.md)

Development configuration under `.codex/`, `.agents/`, `.claude/`, and
`.factory/` is separate from the product runtime. Product-agent prompts,
skills, and workspace resources live under `harness/agent/` and are part of
Harness, not the repository development workflow.
