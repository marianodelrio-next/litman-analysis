---
name: implement
description: Execute an approved design.md through planning, implementation, review, and memory consolidation.
---

Use this skill explicitly with a `.agent-work/` task folder.

1. Require a design.md containing `Approval status: approved`. Otherwise stop and request research-design and human approval.
2. Run `planner` → `coder` → `reviewer` → `memory-manager` sequentially. Planner creates plan.md; Planner and Coder update progress.md at significant milestones.
3. Planner starts from AGENTS.md and docs/codebase-map.md, then reads only relevant architecture, decisions, source, tests, and documentation. Every agent verifies actual code rather than assuming the map is current.
4. If Reviewer finds defects, send concrete guidance to Coder and repeat review. After two unresolved correction rounds, consult advisor when appropriate; if blocked, record it and ask the user. Do not loop indefinitely.
5. Planner does not implement; Reviewer and Advisor are read-only. Memory Manager updates only necessary memory and documentation after a satisfactory review.
6. plan.md must list verifiable steps, affected files or components, tests, and possible regressions. Coder applies only the approved design, updates relevant tests and documentation, and runs validation. Do not declare completion without acceptance criteria and real results.
