# Essential Architecture

LitMan Core is a Python 3.11 application implemented exclusively under `src/litman_core`; the former `litman_analysis` Python package no longer exists. The host CLI validates a job and starts one container. Inside it, `JobRunner` materializes local or Google Drive files, builds a `DocumentBundle`, normalizes documents, and runs either `assessment` or `detailed-analysis`.

Pipelines use `infrastructure/llm/CodexProvider` for structured analysis. Schema, semantic, and evidence validation complete before publishing. `generation/` creates deliverables from the dossier and versioned resources; `infrastructure/storage/` publishes locally or to Drive.

Versioned prompts, rules, schemas, and templates are under `resources/`. The product runs its own Codex CLI in the container; `.codex/` and `.agents/` are development-only configuration and are not part of that runtime.

## Core y Docker

`litman_core` es el namespace público de la aplicación: su `JobRunner` carga y ejecuta un `JobRequest` y contiene el flujo común de materialización, pipelines, validación, generación y publicación. Core no importa ni invoca Docker y no distingue entre runtimes `native` y `docker` en el dominio o los pipelines.

Docker pertenece únicamente a `deployment/docker/` como distribución opcional. La CLI local invoca directamente `JobRunner`; la imagen instala y ejecuta esa misma CLI.

`litman-core` es la CLI canónica y mantiene el alias `litman-analysis`. Los comandos `run`, `assess` y `analyze` ejecutan el runner en el proceso actual; no existe `--native` ni una interfaz worker en el paquete.
