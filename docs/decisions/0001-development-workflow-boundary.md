# 0001 — Separate development workflow from product runtime

Status: accepted
Date: 2026-10-19
Change: CHG-0002

## Context

The repository contains development-agent instructions and a Software Factory
workflow as well as product-agent resources used by LitMan Harness. Keeping
those systems mixed obscures ownership and risks changing product behavior
while maintaining repository tooling.

The former `research-design` and `implement` development skills, their agents,
and `.agent-work/<task>/` folders were retired when the Software Factory was
adopted. The local task folders were subsequently removed.

## Options considered

- Keep development workflow decisions in Core's package decision log.
- Treat all agent resources as one product subsystem.
- Keep cross-repository development tooling at the root, product-agent
  resources with Harness, and record the boundary at repository level.

## Decision

Repository development rules live in `AGENTS.md`. Factory skills and state live
under `.agents/`, `.claude/`, and `.factory/`, and Factory state is managed only
through `swfactory`. Direct changes remain available when authorized by the
person; the Factory is opt-in.

Product-agent prompts, skills, agent definitions, and workspace instructions
remain under `harness/agent/`. They are part of the Harness product runtime and
are not governed as development-agent configuration.

Durable package architecture and product decisions stay in the relevant
package documentation. Cross-package and development-process decisions belong
in this repository decision log.

## Consequences

- Contributors have one operational authority, `AGENTS.md`, and one ownership
  map, `docs/codebase-map.md`.
- Development workflow maintenance does not alter product prompts or the
  product LLM invocation.
- Core's decision log no longer needs to own the cross-repository development
  workflow decision.
