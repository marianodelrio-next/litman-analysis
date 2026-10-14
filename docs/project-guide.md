# Guía de LitMan Analysis

## Arquitectura de ejecución

La interfaz pública es `litman-core run`, que carga `config.toml` y ejecuta directamente `JobRunner`. Docker es opcional y se invoca desde `deployment/docker/compose.yaml`; la configuración y sus rutas se resuelven dentro del contenedor.

Dentro del contenedor, el entrypoint `litman-core` ejecuta el `JobRunner` canónico:

```text
CLI host → un contenedor → origen → inventario/normalización → Codex
                    → validación → publicador → limpieza temporal
```

El runner no conoce Docker. Selecciona `LocalDocumentSource` o `GoogleDriveDocumentSource`, construye un único `DocumentBundle`, ejecuta `AssessmentPipeline` o `DetailedAnalysisPipeline`, valida el run completo y solo entonces usa `LocalArtifactPublisher` o `GoogleDriveArtifactPublisher`. Los IDs y MIME types de Drive se incorporan al bundle en memoria; los hashes se calculan sobre los bytes descargados y llegan a manifests, evidencias y lineage.

| Entrada | Salida | Estado |
|---|---|---|
| Local | Local | Soportada |
| Local | Google Drive | Soportada |
| Google Drive | Local | Soportada |
| Google Drive | Google Drive | Soportada |

## Persistencia y seguridad

- `/app/config.toml` y `/app/input` son mounts de solo lectura.
- `/app/runs` y `/var/lib/litman-core/codex` son persistentes y escribibles.
- `/run/secrets` es de solo lectura; contiene opcionalmente Google y la API key.
- La raíz es de solo lectura y `/tmp` es `tmpfs`.
- El workspace privado se elimina en `finally`; el run y sus diagnósticos no.
- El proceso usa el UID/GID del host y no root.

Codex comparte ahora el contenedor con las credenciales Google. Su entorno conserva solo las variables operativas necesarias y la autenticación elegida; los prompts no mencionan contenido de secretos. `auth.json` debe tener modo `0600`. Nunca guardes claves en jobs, imágenes, manifests o resultados.

No se instala Bubblewrap ni existe un sandbox anidado. Codex se ejecuta con
`--dangerously-bypass-approvals-and-sandbox` y puede acceder al filesystem, la
red y los secretos disponibles en el contenedor. Esta es una decisión aceptada
para la herramienta interna: el contenedor no root, sin capabilities, con raíz
de solo lectura, mounts mínimos y `no-new-privileges` es la frontera de
aislamiento. No montes información ajena al job.

La configuración Docker conserva usuario no root, filesystem de solo lectura,
capabilities eliminadas y `no-new-privileges`; las credenciales se proporcionan
explícitamente sin leer secretos durante las comprobaciones.

## Extensión y operación

Los recursos versionados están en `resources/`; para añadir un origen o publicador implementa los puertos existentes y compón el adaptador en `JobRunner`, sin crear otro orquestador. Toda respuesta de Codex debe pasar la validación estructural y semántica antes de publicarse.

`output.directory` es la raíz local obligatoria de los runs y publicaciones. Antes de ejecutar se asigna una sola vez el `publication_id` con el formato `<job_id>-<timestamp UTC con microsegundos>Z`; el run persistente se crea directamente en `output.directory/<publication_id>/`. Si se configura una réplica Drive, esa misma identidad nombra la carpeta remota y el inventario inmutable de rutas relativas y hashes se replica desde la carpeta local mediante una carpeta temporal y promoción atómica. Con `publication.include_run_files = false`, la carpeta local completa solo se reduce al catálogo final después de validar el inventario y, si corresponde, completar correctamente la réplica Drive; ante cualquier error se conserva el run completo local. Con `true`, se conserva el árbol completo tanto en local como en Drive. `storageQuotaExceeded` se traduce a una recomendación explícita de Shared Drive.

El catálogo cerrado de `detailed-analysis` contiene `resumen_tecnico.docx` (ficha técnica breve y de lectura rápida para técnico, arquitecto o revisor), `guia_preparacion_oferta.docx` (guía operativa para bid manager o redactor), el único DOCX técnico declarado por `generation_manifest.json` y `simulador_economico.xlsx`. Los dos primeros se generan de forma determinista desde `dossier.json`; el ID canónico de la guía es `bid-preparation-guide`.

La salida del análisis y de todos los entregables es siempre española. Las
citas de evidencia, identificadores, nombres de archivo, referencias estables o
de página, nombres propios y fórmulas literales designadas por el schema se
mantienen textualmente como material fuente. En la propuesta técnica,
`output_language` solo acepta `auto` o `es`; el valor heredado `en` se rechaza
para impedir una salida parcial en inglés.

La verificación de evidencias conserva documento y página estrictos. Tolera solamente espacios artificiales introducidos por el layout PDF y registra `verification_method` (`exact` o `layout_whitespace`). Una cita no comprobable produce un informe parcial con advertencias; los fallos estructurales o semánticos continúan siendo bloqueantes.

Consulta el README para autenticación y comandos. Las salidas quedan en el destino indicado y los runs/diagnósticos bajo `runs/`. Antes de cerrar cambios ejecuta pytest, `docker compose -f deployment/docker/compose.yaml config --quiet` y `docker compose -f deployment/docker/compose.yaml build`. Las llamadas reales a Drive requieren autorización explícita; los tests usan fakes.
