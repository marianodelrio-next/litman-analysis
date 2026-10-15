# Essential Architecture

LitMan Core is a Python 3.11 application implemented exclusively under `src/litman_core`; no alternate Core package is shipped. The separate `litman-harness` distribution under `harness/` is a client of Core (see «Harness de expediente»), not an alternate implementation. The CLI validates a job and invokes `JobRunner` in the current Python process. `JobRunner` materializes local or Google Drive files, builds a `DocumentBundle`, normalizes documents, and runs either `assessment` or `detailed-analysis`.

Pipelines use `infrastructure/llm/CodexProvider` for structured analysis. Schema, semantic, and evidence validation complete before publishing. `generation/` creates deliverables from the dossier and versioned resources; `infrastructure/storage/` publishes locally or to Drive.

Versioned prompts, rules, schemas, and templates are under `resources/`. The product invokes an explicitly configured Codex CLI in its execution environment, local or containerized; `.codex/` and `.agents/` are development-only configuration and are not part of the product runtime.

## Core y Docker

`litman_core` es el namespace público de la aplicación: su `JobRunner` carga y ejecuta un `JobRequest` y contiene el flujo común de materialización, pipelines, validación, generación y publicación. Core no importa ni invoca Docker y no distingue entre runtimes `native` y `docker` en el dominio o los pipelines.

Docker pertenece únicamente a `deployment/docker/` como distribución opcional. La CLI local invoca directamente `JobRunner`; la imagen instala y ejecuta esa misma CLI.

El repositorio distingue el desarrollo desde checkout (`deployment/local-dev/`)
del consumo de una wheel instalada (`deployment/local-install/`). Docker es la
frontera de aislamiento y construye la wheel en una etapa intermedia para
instalarla en la imagen final; no usa `src/` como runtime.

`litman-core` es la única CLI pública de Core (el harness expone sus propios `litman` y `litman-mcp`). El comando `run` carga el contrato único `config.toml` en el proceso actual; no existe una interfaz worker en el paquete.
## Proveedores LLM locales

Core usa un único puerto `LLMProvider` y una factoría validada que selecciona
Codex (por defecto) o Claude Code en Ubuntu. La precedencia es `[llm]` del job,
variables del `.env` y valores por defecto; las credenciales permanecen en el
CLI del usuario. Claude recibe únicamente herramientas de lectura y sus cuatro
diagnósticos neutrales se conservan dentro del run. Windows, Docker con Claude
y cancelación explícita no forman parte de este contrato.

## Harness de expediente

`harness/` es la distribución separada `litman-harness`: no importa
`litman_core` y lo invoca como proceso `litman-core run --config` con un
`config.toml` local en un workspace privado, nunca con
`output.google_drive_folder_id` (el publicador de cuenta de servicio de Core no
participa). Su único contrato con Core es la CLI pública: código de salida y
JSON de stdout con los artefactos y sus checksums. Cada empleado usa su OAuth
personal de escritorio con el scope `drive`; el límite a la licitación
conectada lo impone el harness.

Capas: `plans/` (planes y operaciones locales por cuenta), `dossier/`
(pertenencia, inventario del árbol, manifiesto, contexto, incorporación,
publicación, resumen y la recomendación determinista del siguiente paso,
`recommendation.py`),
`analysis/` (originales, ejecución de Core y validación del catálogo público),
`adapters/` (Drive, estado compartido, OAuth, metadatos, documentos, proceso
Core) e `interfaces/` (un registro único de operaciones servido por la CLI
`litman` y el MCP stdio `litman-mcp`). `agent/` contiene las skills y el
subagente lector de producto.

El estado compartido del expediente vive en `_LitMan/manifest.json`
(`litman-dossier-v1`); `contexto.md` se deriva de él. Toda escritura en Drive
pasa por `SharedStateCapability`: con OAuth es `DriveSharedState`
(`adapters/drive_state.py`, actualización condicional con Drive API v2
`If-Match`); el adaptador de metadatos de desarrollo usa
`UnavailableSharedState` y devuelve `pending_concurrency_gate` sin escribir.
Detalle operativo y validación pendiente:
[harness-development.md](harness-development.md).
