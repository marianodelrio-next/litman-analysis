# Contratos vigentes de LitMan Analysis

Este documento fija la línea base de la fase 0. Describe el comportamiento
actual, no una API futura.

## Comandos y ciclo de vida

| Comando | Audiencia | Ciclo | Estado |
|---|---|---|---|
| `litman-analysis run JOB` | integración/operación | carga un job y delega al launcher | vigente |
| `litman-analysis assess CASE` | usuario local | construye un job assessment y delega | vigente |
| `litman-analysis analyze CASE` | usuario local | construye un job detailed-analysis y delega | vigente |
| `litman-analysis-worker run JOB` | contenedor interno | carga el job y ejecuta `JobRunner` | vigente, interno |
| `litman-analysis-worker preflight [runtime\|container]` | operación interna | comprueba aislamiento y Codex | vigente, interno |

`litman-core` es una CLI pública futura; no existe en esta línea base.

## Job y run

Un job contiene `job_id`, `job_type` (`assessment` o `detailed-analysis`),
`input` y `output` (`local` o `google-drive`, cada uno con `location`) y
opciones. El worker no acepta fases independientes. `JobRunner` materializa,
normaliza, analiza, valida y publica atómicamente.

Un run tiene `input/`, `output/` y `logs/`. Ambos pipelines producen
`output/validation.json` y `output/result.json`; detailed-analysis añade
`dossier.json` y `generation_manifest.json`. `lineage.json`, cuando existe,
contiene versión, origen, ruta y SHA-256 del dossier.

## Publicación

La publicación local copia el catálogo completo de `output/**`, además del
manifiesto con hashes. Drive conserva catálogos distintos: assessment publica
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
texto citado cuando están disponibles. El preflight exige usuario no root,
capacidades restringidas, `NoNewPrivs`, directorios esperados y autenticación
de Codex configurada. Drive requiere credenciales explícitas; esta línea base
no usa red, credenciales ni servicios externos en tests.

## Transición

La CLI actual y el worker seguirán siendo las superficies vigentes durante la
transición. `litman-core` queda reservado para una futura separación de Core y
Harness; no se debe inferir equivalencia de sus contratos hasta implementarlo.
