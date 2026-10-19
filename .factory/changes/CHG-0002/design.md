# CHG-0002 — Consolidate and translate the project documentation

## Context

LitMan documents a repository with two independent Python 3.11 distributions. The root documentation describes the shared product and public CLI contract; `core/` and `harness/` own their implementation, operation, and deployment documentation. The Software Factory initialization added development instructions and reference pages alongside the older product documentation.

The current documentation is broadly accurate and its tracked relative links resolve, but ownership is blurred in several places. `README.md`, `docs/product.md`, and `docs/architecture.md` repeat the Core/Harness overview; installation instructions are repeated between the root README and `harness/deployment/README.md`; and development rules overlap across `AGENTS.md`, `docs/conventions.md`, and `docs/working-agreements.md`. The cross-repository development-agent decision is currently stored in `core/docs/decisions.md`. The public contract in `docs/contracts.md` and Core's internal execution description in `core/docs/contracts.md` are intentionally different, but their relationship needs clearer navigation. `harness/docs/development.md` is a 412-line document that combines contributor setup, architecture, operations, durable decisions, product-agent behavior, and pending manual validation.

The maintained product documentation is predominantly Spanish while the Factory working agreement requires published repository artifacts to be English. The person has chosen English for all documentation changed by this work and has explicitly excluded two manuals that are being changed in another task.

## Goal and scope

Create an English, navigable documentation set in which each topic has one identifiable source of truth and each audience has a clear entry point. Preserve verified technical knowledge while reducing repeated procedures and moving cross-repository decisions to the repository-level documentation.

In scope:

- `README.md`, `AGENTS.md`, `CLAUDE.md`, and maintained pages under `docs/`, except the two manuals listed below.
- Documentation owned by Core: `core/README.md`, `core/AGENTS.md`, `core/docs/`, and Markdown files under `core/deployment/`.
- Documentation owned by Harness: `harness/README.md`, `harness/AGENTS.md`, `harness/docs/`, and `harness/deployment/README.md`.
- New repository or package documentation pages needed to give existing material a clear owner.
- Relative links from in-scope documentation to contracts, schemas, examples, code, deployment files, and the excluded manuals.

Out of scope:

- `docs/windows_manual.md` and `docs/validacion_manual_instalacion.md`; both must remain byte-for-byte unchanged because another task owns them.
- Runtime prompts, packaged templates, product-agent skills, agent definitions, and workspace instructions under `core/src/litman_core/resources/` and `harness/agent/`. Their Markdown extension does not make them repository documentation, and changing them could alter product behavior.
- Factory-managed skill copies and state under `.agents/`, `.claude/skills/`, and `.factory/`, apart from this design and normal Factory lifecycle files.
- Product behavior, public schemas, contract semantics, commands, dependencies, deployment behavior, and test configuration.

## Acceptance criteria

- AC-01: All in-scope documentation is written in English, and no CHG-0002 task patch modifies `docs/windows_manual.md` or `docs/validacion_manual_instalacion.md` — verified by: review the complete CHG-0002 changed-file list, confirm both excluded paths are absent from every task patch, and manually inspect every in-scope Markdown file that remains or is added.
- AC-02: A reader can start at `README.md` and reach the canonical product overview, shared architecture, public Core CLI contract, installation guide, contributor rules, Core documentation, and Harness documentation without encountering competing ownership claims — verified by: manually follow each documented audience route and compare the ownership statements with `docs/codebase-map.md`.
- AC-03: Installation, development commands, architecture boundaries, contracts, decisions, and working rules each have one declared source of truth; overview pages summarize and link instead of repeating full procedures — verified by: repository-wide review of repeated headings and command blocks across the in-scope documentation.
- AC-04: The distinction between `docs/contracts.md` as the public process contract and `core/docs/contracts.md` as Core's internal run documentation is explicit from the root, Core, and Harness navigation paths — verified by: manually follow the three navigation paths and confirm each page identifies the appropriate owner and stability boundary.
- AC-05: `harness/docs/development.md` remains a stable contributor entry point while its mixed concerns are moved into clearly named Harness-owned pages for architecture, operations, and durable decisions — verified by: inspect the resulting `harness/docs/` structure and follow every link from `harness/docs/development.md`.
- AC-06: The cross-repository development-agent and Factory decision is recorded under `docs/decisions/` and removed from Core's package decisions without losing its rationale or the distinction between development tooling and product runtime — verified by: compare the new repository decision with the former `Development-agent system` section and inspect `core/docs/decisions.md`.
- AC-07: Every technical statement changed or moved agrees with the current code and configuration, including package names and versions, CLI entry points, the Core/Harness process boundary, supported providers and defaults, Factory checks, and documented test/build commands — verified by: compare against `core/pyproject.toml`, `harness/pyproject.toml`, `core/src/litman_core/cli.py`, `core/src/litman_core/infrastructure/llm/providers.py`, `harness/src/litman_harness/adapters/core.py`, and `.factory/config.toml`; run the repository Factory test and build checks.
- AC-08: All relative links in tracked, in-scope Markdown documentation resolve to existing files, and existing public documentation paths retained as entry points contain no stale references — verified by: run a standard-library Python link scan over tracked in-scope Markdown files and manually inspect links affected by moved content.
- AC-09: `AGENTS.md` remains the complete operational authority and preserves every current repository restriction, validation requirement, Factory rule, work-mode distinction, and instruction-precedence rule after duplicated prose is removed elsewhere — verified by: line-by-line comparison with the pre-change `AGENTS.md` and manual mapping from each original rule to the resulting file.

## Approach

Use a layered information architecture rather than a translation-only pass. Keep `README.md` as the concise audience router, add or maintain a repository documentation index under `docs/`, and keep `docs/codebase-map.md` focused on technical ownership. `docs/product.md`, `docs/architecture.md`, and `docs/contracts.md` remain authoritative for product purpose, cross-package architecture, and the public CLI contract respectively.

Make `AGENTS.md` the operational authority for agent behavior. Keep `docs/conventions.md` for technical repository conventions and `docs/working-agreements.md` for durable collaboration agreements, with links instead of repeated instructions. Record the adoption and boundaries of the development-agent/Factory workflow as a numbered repository decision under `docs/decisions/`, then remove that cross-cutting section from Core's decision log.

Within each package, retain the existing README as its entry point. Core keeps separate internal contracts, operations, decisions, and deployment guides, but removes repeated command sequences where a canonical deployment page already owns them. Harness keeps `harness/docs/development.md` as the stable contributor entry point and splits its current mixed content into `architecture.md`, `operations.md`, and `decisions.md`. Existing paths remain as entry points to reduce link churn.

A translation-only update was rejected because it would preserve the current duplication and unclear ownership. Replacing the documentation with a generated site or adding a documentation framework was rejected because the repository does not need a new dependency or publishing system to solve its navigation and maintenance problems. Renaming or deleting existing entry-point files was rejected because stable paths are more useful than a cosmetically clean tree.

No new product or architecture decision is introduced. The repository-level decision records the already adopted Factory workflow in its proper location; package decisions remain with their owners.

The target ownership map is:

| Topic | Canonical owner |
| --- | --- |
| Audience routing and shortest useful introduction | `README.md` |
| Repository documentation index | `docs/README.md` |
| Product purpose and supported user flows | `docs/product.md` |
| Cross-package architecture and boundaries | `docs/architecture.md` |
| Public Core process contract and versioning | `docs/contracts.md` plus `docs/contracts/` schemas and examples |
| Code and documentation ownership map | `docs/codebase-map.md` |
| Agent operating rules and required validation | `AGENTS.md` |
| Technical repository conventions | `docs/conventions.md` |
| Durable human collaboration agreements | `docs/working-agreements.md` |
| Cross-repository architecture and development-process decisions | `docs/decisions/` |
| End-user and advanced Harness installation | `harness/deployment/README.md` |
| Core package entry point | `core/README.md` |
| Core internals, operations, decisions, and deployment variants | `core/docs/{contracts,operations,decisions}.md` and `core/deployment/` |
| Harness contributor entry point | `harness/docs/development.md` |
| Harness architecture, operations, and durable package decisions | `harness/docs/{architecture,operations,decisions}.md` |
| Executable repository test/build checks | `.factory/config.toml`, documented for contributors in `AGENTS.md` |

`docs/decisions/README.md` will explicitly include durable development-process decisions in its policy. This accommodates the already adopted Factory workflow without presenting it as a new product architecture decision.

## Implementation notes

- Treat code, configuration, schemas, and tests as evidence. Do not change them to make a documentation statement true.
- Preserve exact commands, configuration keys, identifiers, JSON fields, artifact roles, environment variables, file names, and paths when translating prose.
- Do not translate user-entered literals or output examples when doing so would make them cease to represent actual behavior.
- Do not edit `.agents/skills/` and `.claude/skills/` to remove their intentional mirrored copies; `.factory/config.toml` records their template hashes.
- Ignore `.factory/state/` during the documentation inventory. It contains ignored backups and evidence, including superseded documentation snapshots.
- Keep the root public contract schemas and examples in place. This change may improve their navigation but must not alter schema or contract meaning.
- Keep links to the two excluded manuals valid without editing those manuals.
- Verify exclusion by confirming that neither manual appears in any CHG-0002 task patch. Do not compare their final bytes with a moving branch that may receive the concurrent task.
- Preserve `CLAUDE.md` as the minimal `@AGENTS.md` bridge unless a verified client requirement calls for wording around that directive.
- When splitting Harness documentation, move each fact to one owner and replace its old location with a concise link or summary. Avoid copying the same operational sequence into multiple new pages.
- Correct verified wording errors while moving content, including the statement in `core/docs/decisions.md` that currently says `inspect`/`status` would invent the tree; the implementation and Harness documentation show that they traverse it.

## Tasks

```yaml
- id: CHG-0002-01
  title: Establish the repository documentation architecture
  depends_on: []
  complexity: normal
  review: [quality, conformance]
  scope:
    - "README.md"
    - "AGENTS.md"
    - "CLAUDE.md"
    - "docs/README.md"
    - "docs/product.md"
    - "docs/architecture.md"
    - "docs/codebase-map.md"
    - "docs/contracts.md"
    - "docs/conventions.md"
    - "docs/working-agreements.md"
    - "docs/decisions/**"
  acceptance:
    AC-02: manual
    AC-09: manual

- id: CHG-0002-02
  title: Consolidate the Core documentation
  depends_on: [CHG-0002-01]
  complexity: normal
  review: [quality, conformance]
  scope:
    - "core/README.md"
    - "core/AGENTS.md"
    - "core/docs/**"
    - "core/deployment/**/*.md"
  acceptance:
    AC-06: manual

- id: CHG-0002-03
  title: Consolidate the Harness documentation
  depends_on: [CHG-0002-01]
  complexity: normal
  review: [quality, conformance]
  scope:
    - "harness/README.md"
    - "harness/AGENTS.md"
    - "harness/docs/**"
    - "harness/deployment/README.md"
  acceptance:
    AC-05: manual

- id: CHG-0002-04
  title: Reconcile and verify the complete documentation set
  depends_on: [CHG-0002-02, CHG-0002-03]
  complexity: normal
  review: [quality, conformance]
  scope:
    - "README.md"
    - "AGENTS.md"
    - "CLAUDE.md"
    - "docs/README.md"
    - "docs/product.md"
    - "docs/architecture.md"
    - "docs/codebase-map.md"
    - "docs/contracts.md"
    - "docs/conventions.md"
    - "docs/working-agreements.md"
    - "docs/decisions/**"
    - "core/README.md"
    - "core/AGENTS.md"
    - "core/docs/**"
    - "core/deployment/**/*.md"
    - "harness/README.md"
    - "harness/AGENTS.md"
    - "harness/docs/**"
    - "harness/deployment/README.md"
  acceptance:
    AC-01: manual
    AC-02: manual
    AC-03: manual
    AC-04: manual
    AC-05: manual
    AC-06: manual
    AC-07: "bash -lc 'UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv --directory core run pytest -q && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv --directory harness run pytest -q && uv build core --out-dir dist/core && uv build harness --out-dir dist/harness && docker compose -f core/deployment/docker/compose.yaml config --quiet && docker compose -f core/deployment/docker/compose.yaml build'"
    AC-08: manual
    AC-09: manual
```

## Risks and open questions

The main risk is silent semantic drift during translation: precise configuration and contract language can change meaning even when the prose reads naturally. Implementation must compare every changed technical claim with its code or schema owner and retain identifiers verbatim.

Splitting the Harness document can create duplicated explanations or broken inbound links. Keeping `harness/docs/development.md` as an index and running a repository-wide relative-link scan mitigates that risk.

The documentation currently serves Spanish-speaking business users, so changing installation prose to English changes its presentation. This is an explicit decision for this change. Product runtime prompts and agent resources remain outside scope, so their language and behavior do not change.

The two excluded manual documents will remain Spanish and may temporarily use terminology that differs from the new English documentation. Their concurrent owner is responsible for reconciling them later; this change must neither edit them nor require them to be translated for acceptance.

There are no unresolved design questions.
