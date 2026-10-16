# Contrato CLI de LitMan Core

Fuente única del contrato entre `litman-core` y cualquier consumidor (el
harness, que ejecuta Core como proceso sin importar `litman_core`, u otro
sistema). El contrato está versionado (`contract`); su política de cambios
está al final de este documento.

## Comandos

- `litman-core run --config RUTA [--env-file RUTA]`: ejecuta un job. Si se
  omite `--config`, usa `./config.toml`; si no se da `--env-file` y existe un
  `.env` junto a la configuración, se carga sin sobrescribir variables ya
  presentes en el entorno.
- `litman-core info`: imprime versión y contrato sin ejecutar nada.
- `litman-core --version`: texto `litman-core <versión>` (no forma parte del
  contrato versionado; usar `info` para verificación programática).

## Configuración (`config.toml`)

| Clave | Obligatoria | Por defecto |
|---|---|---|
| `job.type` | sí | — (`assessment` o `detailed-analysis`) |
| `job.id` | no | nombre de la carpeta de entrada saneado al patrón `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`; para `input.kind = "google-drive"`, el id de carpeta |
| `input.location` | sí | — |
| `input.kind` | no | `local` (`google-drive` también admitido) |
| `output.directory` | sí | — |
| `output.google_drive_folder_id` | no | sin réplica en Drive |
| `llm.provider` | no | `codex` |
| `llm.model` | no | modelo por defecto del proveedor |
| `publication.include_run_files` | no | `false` |

Cualquier otra clave de primer nivel, o clave no listada dentro de una tabla
anterior, se rechaza (incluida `[analysis]`: no existe superficie pública
para configurar plantillas de generación). Plantilla mínima:
[`docs/contracts/core-config.minimal.toml`](contracts/core-config.minimal.toml).
Plantilla completa, con todas las claves opcionales comentadas:
[`core/deployment/config_example.toml`](../core/deployment/config_example.toml).

## Salida de `run`

Siempre un único objeto JSON en stdout, codificado en UTF-8; stderr sólo para
logs, nunca parte del contrato.

Éxito (código de salida 0):

```json
{"contract": 1, "status": "succeeded", "job_id": "...", "publication_id": "...",
 "local_path": "...",
 "artifacts": [{"role": "technical_summary", "name": "resumen_tecnico.docx",
                "uri": "...", "checksum": "<sha256>"}],
 "remote": {"folder_id": "...", "artifacts": ["..."]}}
```

`remote` sólo aparece si `output.google_drive_folder_id` estaba configurado.

Fallo (código de salida 1):

```json
{"contract": 1, "status": "failed", "local_path": "...",
 "error": {"code": "llm_unavailable", "message": "..."}}
```

`local_path` sólo aparece si el run llegó a crearse antes del fallo.

Uso incorrecto de argumentos (p. ej. subcomando desconocido): código de
salida 2, mensaje de `argparse` en stderr, sin JSON (no es un resultado de
`run`).

Ejemplos completos, uno por tipo de job en éxito y uno por código en fallo:
[`docs/contracts/examples/`](contracts/examples/). Esquema:
[`docs/contracts/core-result.schema.json`](contracts/core-result.schema.json).

### Roles de artefacto

Conjunto cerrado: `opportunity_report`, `technical_summary`,
`bid_preparation_guide`, `technical_document`, `economic_simulator`. Además,
`run_file` aparece exclusivamente cuando `publication.include_run_files =
true`, etiquetando cualquier archivo publicado fuera del catálogo de
entregables (el harness nunca lo ve: publica siempre con
`include_run_files = false`).

### Códigos de error (conjunto cerrado)

| Código | Origen |
|---|---|
| `invalid_config` | configuración TOML, `Settings` o `.env` inválidos, antes de ejecutar el job |
| `invalid_input` | materialización del expediente, inventario, normalización, metadatos de entrada de Drive, tamaño |
| `llm_unavailable` | binario del proveedor LLM inexistente o autenticación inválida (Codex o Claude Code) |
| `analysis_failed` | timeout, respuesta inválida del proveedor, generación de entregables, run no validado |
| `publication_failed` | publicación local o en Drive |
| `internal` | cualquier otro fallo no clasificado |

## Salida de `info`

```json
{"contract": 1, "version": "0.1.0", "providers": ["claude-code", "codex"]}
```

Esquema: [`docs/contracts/core-info.schema.json`](contracts/core-info.schema.json).

## Versionado del contrato

Todo resultado de `run` e `info` lleva `contract: 1`.

- Sube `contract` al eliminar o renombrar un campo, cambiar su significado o
  el de un valor existente, o añadir un nuevo `status`.
- No sube al añadir campos opcionales nuevos, roles nuevos o códigos de error
  nuevos.
- Un consumidor debe tratar un código de error desconocido como `internal` y
  un rol de artefacto desconocido como error de contrato (el conjunto de
  roles es cerrado salvo adiciones futuras explícitas).
- Un `contract` distinto del esperado por el consumidor es incompatibilidad
  de contrato, no un error de ejecución del job.

## Para consumidores

El harness mantiene fijado `litman-core==0.1.0`; la comprobación de
`contract` es la red de seguridad frente a instalaciones distintas,
especialmente para cualquier otro sistema que dependa de esta CLI.
`core/docs/contracts.md` describe, además, la estructura interna del run
(`input/`, `output/`, lineage, publicación), que no forma parte de este
contrato y puede cambiar sin subir `contract`.
