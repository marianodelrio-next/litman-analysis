# Product

## Purpose

LitMan supports the evaluation of procurement opportunities and the management
of their working dossiers. [Core](../core/README.md) performs the analysis;
[Harness](../harness/README.md) manages the dossier and publication workflow.
The packages communicate only through Core's versioned
[public CLI contract](contracts.md).

## Audiences and supported flows

- Business users can install Harness and Core together, connect a Google Drive
  folder with personal OAuth, and work through Codex or Claude. The
  [Harness installation guide](../harness/deployment/README.md) owns this setup.
- Users who only need local procurement analysis can install and run Core on
  its own. The [Core entry point](../core/README.md) owns that route.
- Integrators can invoke `litman-core` as a process and consume its versioned
  JSON output. The [public CLI contract](contracts.md) is the stable interface.
- Contributors work on Core and Harness as separate distributions and follow
  the root [development rules](../AGENTS.md).

## Product boundary

The Software Factory, Orca workspaces, and development-agent skills in the
repository root are development tooling. They are not part of the LitMan
product runtime. Product-agent resources are owned separately by
`harness/agent/`.

Harness does not import Core's Python modules. It invokes `litman-core` as a
child process, validates the public result, and publishes the selected
artifacts. See the [shared architecture](architecture.md) for this boundary and
the package documentation for internal behavior.
