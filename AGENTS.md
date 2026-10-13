# Codex Development

LitMan Analysis is a Python 3.11 service that analyzes procurement files in Docker. This repository also contains a Codex-only development workflow; it is separate from the product runtime.

- Make the smallest scoped change and follow existing architecture and conventions.
- Prefer conventional, deterministic code, scripts, rules, and templates; do not delegate work to an LLM that they can solve reliably.
- Do not add dependencies, abstractions, refactors, or product changes outside the authorized scope.
- Functional changes require relevant tests, real results, and affected documentation updates. Do not claim completion before acceptance criteria are checked.
- Do not use real credentials, Drive, destructive operations, or production resources without explicit authorization.
- Do not alter the product Codex CLI invocation, Docker isolation, product prompts, schemas, templates, or pipelines unless explicitly requested.

Run `UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q`; when relevant, also run `docker compose config --quiet` and `docker compose build`.

Start with `AGENTS.md`, then use the [codebase map](docs/codebase-map.md) to locate relevant code. Read [architecture](docs/architecture.md) and [decisions](docs/decisions.md) only when relevant; verify the actual code and expand exploration only as needed.

## Work modes

Choose the mode from the user's explicit request.

### Direct change (default)

When the user asks to change, fix, add, remove, or update a scoped part of the
repository, make the change directly. Do not create `.agent-work/`, `design.md`,
`progress.md`, or `plan.md`, and do not invoke `research-design` or `implement`
unless the user explicitly requests that workflow.

Inspect the relevant code, make the smallest scoped change, update affected
tests and documentation, and run validation proportionate to the change.

### Research and design workflow (opt-in)

Use `research-design` only when the user explicitly asks to investigate
interactively, create a design/task, seek design approval, or use the
multi-agent implementation workflow.

Use `implement` only when the user explicitly requests it and an approved
`design.md` exists. Its `planner` → `coder` → `reviewer` → `memory-manager`
sequence applies only within that workflow.

Task memory lives in untracked `.agent-work/<task>/`; create it only for this
opt-in workflow and keep it concise.
