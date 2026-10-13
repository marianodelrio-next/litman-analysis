# Durable Technical Decisions

## Development-agent system

- Development agents live in `AGENTS.md`, `.codex/`, and `.agents/`; they are isolated from the product pipeline and its Codex CLI.
- Tasks that opt into the design workflow use untracked local memory in
  `.agent-work/<task>/`. A design.md requires human approval before `implement`;
  authorized direct changes may proceed without that workflow.
- Global memory is limited to essential architecture, durable decisions, and a navigation map. Memory Manager updates it after a satisfactory review.
- Coordination allows at most three concurrent subagents. Implementation remains sequential to avoid contention on shared files.

## Application namespace and Docker boundary

- `litman_core` is the only Python application package and owns CLI, worker, orchestration, domain, pipelines, infrastructure, generation, configuration, and packaged resources.
- The former `litman_analysis` Python package is removed rather than retained as a compatibility implementation.
- `litman-core` and `litman-core-worker` are canonical entry points. Historical command names may remain only as aliases targeting `litman_core` modules.
- Docker remains the external distribution and isolation boundary; domain and pipelines do not select or branch on runtime.
