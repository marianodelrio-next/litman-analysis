# Essential Architecture

LitMan Core is a Python 3.11 application implemented exclusively under `src/litman_core`; no alternate Python package is shipped. The CLI validates a job and invokes `JobRunner` in the current Python process. `JobRunner` materializes local or Google Drive files, builds a `DocumentBundle`, normalizes documents, and runs either `assessment` or `detailed-analysis`.

Pipelines use `infrastructure/llm/CodexProvider` for structured analysis. Schema, semantic, and evidence validation complete before publishing. `generation/` creates deliverables from the dossier and versioned resources; `infrastructure/storage/` publishes locally or to Drive.

Versioned prompts, rules, schemas, and templates are under `resources/`. The product invokes an explicitly configured Codex CLI in its execution environment, local or containerized; `.codex/` and `.agents/` are development-only configuration and are not part of the product runtime.

## Core y Docker

`litman_core` es el namespace público de la aplicación: su `JobRunner` carga y ejecuta un `JobRequest` y contiene el flujo común de materialización, pipelines, validación, generación y publicación. Core no importa ni invoca Docker y no distingue entre runtimes `native` y `docker` en el dominio o los pipelines.

Docker pertenece únicamente a `deployment/docker/` como distribución opcional. La CLI local invoca directamente `JobRunner`; la imagen instala y ejecuta esa misma CLI.

El repositorio distingue el desarrollo desde checkout (`deployment/local-dev/`)
del consumo de una wheel instalada (`deployment/local-install/`). Docker es la
frontera de aislamiento y construye la wheel en una etapa intermedia para
instalarla en la imagen final; no usa `src/` como runtime.

`litman-core` es la única CLI pública. El comando `run` carga el contrato único `config.toml` en el proceso actual; no existe una interfaz worker en el paquete.
