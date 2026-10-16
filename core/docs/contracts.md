# Contratos vigentes de LitMan Core

Describe el comportamiento actual de Core, no una API futura.

## Comandos y ciclo de vida

| Comando | Audiencia | Ciclo | Estado |
|---|---|---|---|
| `litman-core run` | usuario local | carga `./config.toml` (y su `.env` adyacente) y ejecuta `JobRunner` | canónico |
| `litman-core run --config RUTA [--env-file RUTA]` | usuario local, integración (harness) | carga una configuración y un `.env` explícitos | canónico |
| `litman-core info` | integración (harness) | imprime versión y contrato | canónico |

El contrato de la CLI (claves de configuración, forma exacta del JSON de
`run`/`info`, roles de artefacto, códigos de error y política de
versionado) vive en [`docs/contracts.md`](../../docs/contracts.md); no se
repite aquí.

## Job y run

Un job contiene `job.type` (`assessment` o `detailed-analysis`),
`input.location` y `output.directory` como claves obligatorias, además de
`job.id`, `input.kind`, `output.google_drive_folder_id`, `[llm]` y
`[publication]` opcionales (ver el contrato enlazado arriba). `JobRunner`
materializa, normaliza, analiza, valida y publica atómicamente.

Cada ejecución crea una publicación identificada por un `publication_id` y un
run con `input/`, `output/` y `logs/`. Ambos pipelines producen
`output/validation.json` y `output/result.json`; detailed-analysis añade
`dossier.json`, `generation_manifest.json` y su `lineage.json`, que contiene
versión, origen, ruta y SHA-256 del dossier.

## Publicación

Ambos destinos publican el mismo catálogo cerrado, sin diagnósticos, lineage ni
manifiesto de publicación: assessment publica
la ficha PDF; detailed-analysis publica los dos resúmenes, un DOCX técnico y
el simulador económico según el manifiesto. Drive usa carpeta temporal y solo
la renombra tras completar la subida.

El catálogo público se construye desde el run de cada `publication_id`; los
archivos internos permanecen en el run local según la configuración de
publicación. Los hashes se calculan sobre los bytes de cada ejecución. No se comparan entre
ejecuciones. Un `validation.json` inválido, un artefacto ausente o una subida
incompleta impide presentar el run como éxito.

## Versiones, evidencias y runtime

Los pipelines declaran sus bundles versionados y sus hashes; los resultados
de validación incluyen errores de schema, semántica y evidencias. Las
referencias de documentos conservan identificador, nombre, MIME, páginas o
texto citado cuando están disponibles. Drive requiere credenciales explícitas;
esta línea base no usa red, credenciales ni servicios externos en tests. Las
comprobaciones de usuario, capabilities, mounts y `no-new-privileges` son
preflight opcional de `deployment/docker`, no parte del contrato de Core.
