# Essential Architecture

LitMan Core is a Python 3.11 application implemented exclusively under `src/litman_core`; the former `litman_analysis` Python package no longer exists. The host CLI validates a job and starts one container. Inside it, `JobRunner` materializes local or Google Drive files, builds a `DocumentBundle`, normalizes documents, and runs either `assessment` or `detailed-analysis`.

Pipelines use `infrastructure/llm/CodexProvider` for structured analysis. Schema, semantic, and evidence validation complete before publishing. `generation/` creates deliverables from the dossier and versioned resources; `infrastructure/storage/` publishes locally or to Drive.

Versioned prompts, rules, schemas, and templates are under `resources/`. The product runs its own Codex CLI in the container; `.codex/` and `.agents/` are development-only configuration and are not part of that runtime.

## Core y Docker

`litman_core` es el namespace público de la aplicación: su `JobRunner` carga y ejecuta un `JobRequest` y contiene el flujo común de materialización, pipelines, validación, generación y publicación. Core no importa ni invoca Docker y no distingue entre runtimes `native` y `docker` en el dominio o los pipelines.

Docker pertenece a la capa de distribución y aislamiento. `ContainerJobLauncher` vive en `litman_core.execution` como adaptador del host, mientras `litman_core.worker` es el entrypoint dentro del contenedor. Ambos invocan el mismo `litman_core.JobRunner`; el worker puede añadir el preflight propio del contenedor, pero no duplica el motor.

`litman-core` es la CLI canónica. Los comandos instalados `litman-analysis` y `litman-analysis-worker` son aliases temporales que apuntan directamente a módulos de `litman_core`; no corresponden a un segundo paquete. La CLI host conserva Docker como comportamiento predeterminado para compatibilidad. `--native` llama directamente a Core y no introduce una rama de runtime en los contratos de aplicación.
