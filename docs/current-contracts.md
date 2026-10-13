# Contratos vigentes de LitMan Core

Este documento fija la línea base de la fase 0. Describe el comportamiento
actual, no una API futura.

## Comandos y ciclo de vida

| Comando | Audiencia | Ciclo | Estado |
|---|---|---|---|
| `litman-core run JOB` | integración/operación | carga un job y ejecuta `JobRunner` directamente | canónico |
| `litman-core assess CASE` | usuario local | construye un job assessment y delega | canónico |
| `litman-core analyze CASE` | usuario local | construye un job detailed-analysis y delega | canónico |
| `litman-analysis` | compatibilidad | alias de la CLI de `litman_core` | temporal |

Toda la implementación pertenece al paquete `litman_core`; no existe un paquete Python `litman_analysis` de compatibilidad.

## Job y run

Un job contiene `job_id`, `job_type` (`assessment` o `detailed-analysis`),
`input` y `output` (`local` o `google-drive`, cada uno con `location`) y
opciones. `JobRunner` materializa,
normaliza, analiza, valida y publica atómicamente.

Un run tiene `input/`, `output/` y `logs/`. Ambos pipelines producen
`output/validation.json` y `output/result.json`; detailed-analysis añade
`dossier.json` y `generation_manifest.json`. `lineage.json`, cuando existe,
contiene versión, origen, ruta y SHA-256 del dossier.

## Publicación

Ambos destinos publican el mismo catálogo cerrado, sin diagnósticos, lineage ni
manifiesto de publicación: assessment publica
la ficha PDF; detailed-analysis publica los dos resúmenes, un DOCX técnico y
el simulador económico según el manifiesto. Drive usa carpeta temporal y solo
la renombra tras completar la subida.

Los hashes se calculan sobre los bytes de cada ejecución. No se comparan entre
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

## Transición

Los nombres de comando históricos se conservan temporalmente como aliases de
los mismos entry points de Core. Su retirada futura no afecta al namespace
Python ni implica mantener una segunda implementación.
