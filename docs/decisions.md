# Durable Technical Decisions

## Development-agent system

- Development agents live in `AGENTS.md`, `.codex/`, and `.agents/`; they are isolated from the product pipeline and its Codex CLI.
- Tasks use untracked local memory in `.agent-work/<task>/`. A design.md requires human approval before implement.
- Global memory is limited to essential architecture, durable decisions, and a navigation map. Memory Manager updates it after a satisfactory review.
- Coordination allows at most three concurrent subagents. Implementation remains sequential to avoid contention on shared files.
