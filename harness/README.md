# LitMan Harness

`litman-harness` manages a procurement dossier in Google Drive through each
employee's personal OAuth account. It exposes the same operations through the
`litman` command-line interface and the `litman-mcp` stdio server, and runs
LitMan Core only as the separate `litman-core` process installed in the same
Python environment.

Choose the route that matches your goal:

- [Install or maintain LitMan](deployment/README.md), either with the guided
  installer or from wheels in an IT-managed environment.
- [Contribute to the Harness](docs/development.md), starting with the local
  development setup and the Harness documentation map.
- Review the Harness [architecture](docs/architecture.md),
  [operations and recovery model](docs/operations.md), or
  [durable decisions](docs/decisions.md).
- Review the repository-owned [public Core process contract](../docs/contracts.md)
  when changing the Core/Harness boundary. Core's
  [internal run documentation](../core/docs/contracts.md) is not a Harness
  integration contract.

Repository-wide architecture, ownership, and contributor rules remain in the
[root documentation](../docs/index.md), [codebase map](../docs/codebase-map.md),
and [AGENTS.md](../AGENTS.md).
