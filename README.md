# LitMan

LitMan helps people evaluate procurement opportunities and manage the resulting
dossier. It is distributed as two independent Python 3.11 packages:

- [LitMan Core](core/README.md) analyzes procurement files locally or in
  optional Docker isolation.
- [LitMan Harness](harness/README.md) manages a dossier in Google Drive with a
  person's OAuth account and runs Core through its public CLI.

Each package has its own project, lockfile, development environment, tests,
and operational documentation. Start with the [product overview](docs/product.md)
for supported user flows or the [shared architecture](docs/architecture.md) for
the boundary between the packages.

## Choose a route

- **Analyze files with Core only:** start with the
  [Core documentation](core/README.md).
- **Manage complete dossiers in Google Drive:** use the canonical
  [installation guide](harness/deployment/README.md), then follow the
  [Harness documentation](harness/README.md).
- **Integrate with Core:** use the versioned
  [public CLI contract](docs/contracts.md). Core's
  [internal run documentation](core/docs/contracts.md) describes implementation
  details and is not part of that public contract.
- **Contribute to LitMan:** read the complete [agent and contributor rules](AGENTS.md),
  then use the [codebase map](docs/codebase-map.md) to find the owning package.

The [documentation index](docs/README.md) lists every canonical topic and the
entry points for Core and Harness.
