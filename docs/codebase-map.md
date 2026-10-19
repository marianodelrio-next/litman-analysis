# Codebase map

Use this index to identify the owner of a change, then verify the current code
before editing it.

| Area | Paths | Ownership |
| --- | --- | --- |
| Repository documentation and development tooling | `README.md`, `AGENTS.md`, `docs/`, `.codex/`, `.agents/`, `.claude/`, `.factory/changes/` | Cross-package product documentation, contributor rules, and development workflow. These are not product runtime resources. |
| Versioned CLI contract | `docs/contracts.md`, `docs/contracts/` | Public source of truth for `litman-core run` and `info`, including schemas, examples, and the minimal Harness configuration. |
| Core distribution | `core/pyproject.toml`, `core/uv.lock`, `core/README.md` | Package metadata for `litman-core` and the Core documentation entry point. |
| Core execution | `core/src/litman_core/cli.py`, `core/src/litman_core/errors.py`, `core/src/litman_core/execution/job_runner.py`, `core/src/litman_core/application/` | CLI behavior, closed error mapping, job loading, and local analysis orchestration. |
| Core domain and generation | `core/src/litman_core/domain/`, `core/src/litman_core/pipelines/`, `core/src/litman_core/generation/`, `core/src/litman_core/resources/` | Job model, analysis, validation, versioned pipelines, artifact generation, and packaged runtime resources. |
| Core infrastructure | `core/src/litman_core/infrastructure/` | Document processing, storage, run metadata, and LLM providers. |
| Core operations | `core/deployment/`, `core/tests/`, `core/docs/` | Core deployment, tests, internal run documentation, operations, and package decisions. |
| Harness distribution | `harness/pyproject.toml`, `harness/uv.lock`, `harness/README.md` | Package metadata for `litman-harness` and the Harness documentation entry point. |
| Harness interfaces and Core adapter | `harness/src/litman_harness/interfaces/`, `harness/src/litman_harness/adapters/core.py` | The `litman` and `litman-mcp` interfaces and execution of Core as a process. |
| Dossier workflow | `harness/src/litman_harness/dossier/`, `harness/src/litman_harness/analysis/`, `harness/src/litman_harness/plans/`, `harness/src/litman_harness/adapters/` | Dossier state, local plans, personal OAuth Drive access, and publication. |
| Harness product resources and operations | `harness/agent/`, `harness/src/litman_harness/installation.py`, `harness/deployment/`, `harness/tests/`, `harness/docs/` | Product-agent resources, guided and advanced installation, tests, and Harness-owned documentation. |

The [public CLI contract](contracts.md) defines the stable interface between
the packages. For package internals, use the [Core documentation](../core/README.md)
or [Harness documentation](../harness/README.md).
