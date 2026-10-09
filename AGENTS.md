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

Use `research-design` before implementation. `implement` requires a human-approved task `design.md`. Task memory lives in untracked `.agent-work/<task>/`; keep it concise.
