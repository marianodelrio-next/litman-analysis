# Product

## What it is

LitMan has two Python 3.11 distributions. [Core](../core/README.md) analyzes procurement files locally or in optional Docker isolation. [Harness](../harness/README.md) manages a procurement dossier in Google Drive using a person's OAuth account and runs Core through its public CLI. See the [architecture](architecture.md) and [shared contract](contracts.md).

## Who it is for

The documented installation serves business users working on procurement dossiers through Codex or Claude. Core also supports a standalone analysis flow without Harness. See the [root README](../README.md) for the two installation paths.

## What it is not

The Software Factory and development agent skills in the repository root are development tooling, not part of the LitMan product runtime. Harness does not run Core by importing its Python modules; the process boundary and output schema are part of the [public contract](contracts.md).

## Main flows

- Standalone Core analysis: local inputs and configuration enter `litman-core`; outputs follow the versioned CLI contract. See [Core operations](../core/docs/operations.md).
- Dossier management: `litman` or `litman-mcp` inspects a connected Drive folder, previews changes, applies a person's accepted plan, runs Core, and publishes results. See [Harness development](../harness/docs/development.md).
- End user setup: guided installation registers the product skills, MCP server, and workspace. See [Harness deployment](../harness/deployment/README.md).
