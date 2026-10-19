# Working agreements

These agreements record durable collaboration choices. The complete and
current operational instructions are in [AGENTS.md](../AGENTS.md).

## Change process

- Scoped repository changes use direct-change mode by default. The Software
  Factory is an opt-in workflow used only when a person explicitly requests
  it. (2026-10-19)
- Factory state is changed only through `swfactory`; designs require explicit,
  named human approval before implementation. (2026-10-19)

## Ownership and scope

- Changes stay within their authorized package and avoid unrelated
  dependencies, refactors, or product behavior. (2026-10-19)
- Core and Harness retain separate ownership, with their public interaction
  governed by the root CLI contract. (2026-10-19)

## Evidence

- Functional claims require relevant tests and real results. Factory tasks
  close only after their configured checks and acceptance criteria have been
  verified. (2026-10-19)

## Communication

- Repository artifacts are written in English; agent conversation follows the
  person's language. (2026-10-19)
