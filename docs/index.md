# Documentation

This index routes readers to the canonical owner of each topic. Overview pages
summarize and link; package documentation owns implementation and operations.

## Product and integration

| Topic | Canonical page |
| --- | --- |
| Product purpose and supported user flows | [Product](product.md) |
| Boundary between Core and Harness | [Shared architecture](architecture.md) |
| Stable `litman-core` process interface | [Public CLI contract](contracts.md) |
| Source and documentation ownership | [Codebase map](codebase-map.md) |

The public contract above is the interface for Harness and other process
consumers. [Core's internal run contract](../core/docs/contracts.md) documents
workspace layout, lineage, and internal publication behavior; it is not a
public compatibility promise.

## Installation and package documentation

- [Harness installation](../harness/deployment/README.md) is the canonical
  end-user and advanced installation guide.
- [Core documentation](../core/README.md) covers standalone analysis and links
  to Core operations, deployment, and decisions.
- [Harness documentation](../harness/README.md) covers dossier management and
  links to Harness development and operations.

## Contributing

- [AGENTS.md](../AGENTS.md) is the complete operational authority for agents,
  scope, validation, and Factory use.
- [Repository conventions](conventions.md) define technical and documentation
  conventions without repeating operational rules.
- [Working agreements](working-agreements.md) record durable collaboration
  choices.
- [Repository decisions](decisions/README.md) record cross-package and durable
  development-process decisions. Package decisions remain with Core or
  Harness.
- [Releasing LitMan](releasing.md) is the scripted, documented release flow:
  the single product version, `CHANGELOG.md`, and `scripts/release.py`.
- [CHANGELOG.md](../CHANGELOG.md) records every user-visible change, by
  version.