---
name: research-design
description: Investigate a bug, improvement, feature, or architecture change interactively, and create a reviewable design only on explicit request.
---

Use this skill when the user wants structured research, an explicit design, or
the multi-agent `implement` workflow. It is optional: authorized direct changes
do not require a task folder or a design.

## Modes

### `research` (default)

Use this mode for interactive exploration. Read `AGENTS.md`, use
`docs/codebase-map.md` to locate relevant modules, and read architecture or
decisions only when relevant. Inspect only needed source, tests, and
documentation; verify actual behavior and expand exploration only when needed.

- Discuss findings, evidence, alternatives, trade-offs, recommendations, and
  open questions with the user across as many turns as needed.
- Do not create or modify `.agent-work`, product code, or durable documentation.
- Treat “investiga”, “analiza”, “compara”, and “propón” as `research` requests.
- Use the `researcher` agent for a bounded delegated investigation or second
  opinion when it adds value. Bring its findings back to the conversation; it
  must not create a task unless explicitly asked.
- Consult `advisor` only for a difficult, specific question with evidence,
  alternatives, and constraints.

### `create-design`

Enter this mode only when the user explicitly asks to create a task or design,
for example: “crea la tarea”, “redacta el design.md”, or “prepara el diseño para
aprobación”. Do not infer this intent from a possible implementation.

1. Create `.agent-work/<kebab-case-task-name>/`, adding a short suffix on
   collision. Create `design.md` and `progress.md` only there.
2. Reuse the conclusions already agreed in `research`; perform only the extra
   verification necessary to make the design reviewable.
3. Assess current behavior, constraints, and alternatives. Prefer reuse and
   simple deterministic solutions.
4. `design.md` must contain: objective and problem; current behavior; proposed
   solution; relevant alternatives and rationale; affected components;
   acceptance criteria; required tests; risks or open questions. Start it with
   `Approval status: pending`.
5. Keep `progress.md` concise: current status, last completed step, tests and
   results, blockers, next action, and review status.
6. Present the design and wait for human approval. Do not invoke `implement`.
   After explicit approval, set `Approval status: approved`; keep it pending
   when the user requests revisions.
