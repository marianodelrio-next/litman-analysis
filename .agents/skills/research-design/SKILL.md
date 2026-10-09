---
name: research-design
description: Investigate a bug, improvement, feature, or architecture change and prepare a reviewable design before implementation.
---

Use this skill explicitly before changing code.

1. Create `.agent-work/<kebab-case-task-name>/`, adding a short suffix on collision. Create design.md and progress.md only there.
2. Have `researcher` read AGENTS.md, use docs/codebase-map.md to identify relevant modules, then read architecture or decisions only when relevant. Inspect only needed source, tests, and documentation; verify actual code and expand exploration only when needed.
3. Assess current behavior, constraints, and alternatives. Prefer reuse and simple deterministic solutions. Consult `advisor` only for a difficult question with a concrete question, evidence, alternatives, and constraints.
4. design.md must contain: objective and problem; current behavior; proposed solution; relevant alternatives and rationale; affected components; acceptance criteria; required tests; risks or open questions. Start it with `Approval status: pending`.
5. Keep progress.md concise: current status, last completed step, tests and results, blockers, next action, and review status.
6. Present the design and wait for human approval. Do not modify product code or invoke implement. After explicit approval, set `Approval status: approved` in design.md; keep it pending when the user requests revisions.
