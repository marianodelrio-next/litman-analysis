# Essential Architecture

LitMan Analysis is a Python 3.11 application under `src/litman_analysis`. The host CLI validates a job and starts one container. Inside it, `JobRunner` materializes local or Google Drive files, builds a `DocumentBundle`, normalizes documents, and runs either `assessment` or `detailed-analysis`.

Pipelines use `infrastructure/llm/CodexProvider` for structured analysis. Schema, semantic, and evidence validation complete before publishing. `generation/` creates deliverables from the dossier and versioned resources; `infrastructure/storage/` publishes locally or to Drive.

Versioned prompts, rules, schemas, and templates are under `resources/`. The product runs its own Codex CLI in the container; `.codex/` and `.agents/` are development-only configuration and are not part of that runtime.
