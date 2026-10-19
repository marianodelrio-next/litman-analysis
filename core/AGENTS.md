# Core development

Follow the repository [AGENTS.md](../AGENTS.md) and use the [codebase map](../docs/codebase-map.md) to locate changes. Core owns local procurement analysis, the public `litman-core` CLI, and optional Docker deployment. Its internal decisions are in [core/docs/decisions.md](docs/decisions.md).

For Core changes, run `UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q` from `core/`. When Docker is affected, also run the Compose configuration and build checks specified in the root instructions. Keep the public contract in [docs/contracts.md](../docs/contracts.md) synchronized with interface changes.
