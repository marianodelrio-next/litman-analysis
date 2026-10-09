# Codebase Map

Use this map to locate likely ownership, then verify the current code before editing.

| Area | Paths | Navigation purpose |
| --- | --- | --- |
| Package and configuration | `src/litman_core/config.py`, `src/litman_core/resource_paths.py`, `src/litman_core/runtime.py` | Package settings, resource resolution, runtime directories. |
| Host entry points | `src/litman_core/cli.py`, `src/litman_core/execution/container_launcher.py` | Public commands and host-to-container job handoff. |
| Container entry point | `src/litman_core/worker.py`, `src/litman_core/execution/job_runner.py` | Worker commands, preflight, job orchestration, source/pipeline/publisher selection. |
| Job contract | `src/litman_core/application/job_loader.py`, `src/litman_core/domain/jobs.py`, `src/litman_core/resources/schemas/job.schema.json` | Job loading, validation, and job types. |
| Document input | `src/litman_core/infrastructure/documents/`, `src/litman_core/infrastructure/storage/local.py`, `src/litman_core/infrastructure/storage/google_drive.py` | Inventory, normalization, local sources, and Drive materialization. |
| Drive integration | `src/litman_core/infrastructure/storage/google_drive.py`, `src/litman_core/infrastructure/storage/publication.py` | Google API setup, Drive reads, staged publication, publication naming. |
| Product Codex CLI | `src/litman_core/infrastructure/llm/codex_cli.py`, `src/litman_core/infrastructure/llm/codex_auth.py`, `src/litman_core/infrastructure/llm/codex_events.py` | Authentication, `codex exec`, event capture, and LLM failures. |
| Pipeline framework | `src/litman_core/pipelines/runner.py`, `src/litman_core/pipelines/registry.py`, `src/litman_core/pipelines/models.py` | Versioned resource loading and common pipeline execution. |
| Assessment analysis | `src/litman_core/pipelines/assessment/`, `src/litman_core/resources/pipelines/assessment/v1/` | Assessment preparation, extraction, rules, and prompts. |
| Detailed analysis | `src/litman_core/pipelines/detailed_analysis/`, `src/litman_core/resources/pipelines/detailed/v1/` | Dossier extraction and detailed-analysis prompts. |
| Validation | `src/litman_core/domain/validation/`, `src/litman_core/resources/schemas/` | Schema, semantic, and evidence validation. |
| Document generation | `src/litman_core/generation/service.py`, `src/litman_core/generation/registry.py`, `src/litman_core/generation/*/generator.py`, `src/litman_core/generation/*/renderer.py` | Deterministic artefact planning and DOCX/XLSX/PDF rendering. |
| Versioned templates | `src/litman_core/resources/templates/` | Runtime document and spreadsheet templates. |
| Run metadata | `src/litman_core/infrastructure/runs.py` | Run directories, hashes, manifests, and lineage. |
| Unit tests: domain/pipelines | `tests/unit/domain/`, `tests/unit/pipelines/`, `tests/unit/test_worker_phases.py` | Validation, pipeline behavior, and worker phases. |
| Unit tests: infrastructure | `tests/unit/infrastructure/` | Storage, normalization, product Codex CLI, and auth. |
| Unit tests: generation | `tests/unit/generation/` | Artefact generation and rendering. |
| Contracts and integration | `tests/contracts/`, `tests/integration/test_job_runner.py` | Public job and architecture contracts; end-to-end job orchestration. |

Project-level operating guidance is in `AGENTS.md`; concise architecture and durable decisions are in `docs/architecture.md` and `docs/decisions.md`.
