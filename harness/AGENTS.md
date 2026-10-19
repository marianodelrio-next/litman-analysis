# Harness development

Follow the repository [AGENTS.md](../AGENTS.md) and use the [codebase map](../docs/codebase-map.md) to locate changes. Harness owns dossier management, OAuth-based Drive access, and the `litman` and `litman-mcp` interfaces. Start with the [Harness development guide](docs/development.md); package architecture, operations, and decisions are linked from there.

For Harness changes, run `UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q` from `harness/`. Preserve the process boundary to Core and update the [shared contract](../docs/contracts.md) when its public interface changes. Keep product agent resources under `harness/agent/` separate from development skills.
