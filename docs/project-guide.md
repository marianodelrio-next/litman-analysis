# Guía de LitMan Analysis

## Arquitectura de ejecución

La interfaz pública (`litman-analysis run`, `assess` y `analyze`) se ejecuta en el host. `ContainerJobLauncher` valida el job, convierte únicamente las rutas locales a `/input` y `/output`, crea un contrato interno en un directorio privado y lanza una sola instancia del servicio `litman-analysis`.

Dentro del contenedor, `litman-analysis-worker run` carga el contrato y delega en el `JobRunner` canónico:

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

- `/job` y `/input` son mounts de solo lectura.
- `/output`, `/data/runs` y `/var/lib/litman-analysis/codex` son persistentes y escribibles.
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

Usa `litman-analysis-worker preflight runtime` para validar UID/GID,
capabilities, `NoNewPrivs`, mounts y autenticación sin leer secretos. Usa
`preflight container` para una comprobación integral con `fixture.md`; registra
la conectividad observada, pero no exige que la red esté aislada.

## Extensión y operación

Los recursos versionados están en `resources/`; para añadir un origen o publicador implementa los puertos existentes y compón el adaptador en `JobRunner`, sin crear otro orquestador. Toda respuesta de Codex debe pasar la validación estructural y semántica antes de publicarse.

Cada publicación local o Drive crea una carpeta única bajo `output.location`, con el formato `<job_id>-<timestamp UTC>`. Esto conserva cada relanzamiento del mismo job. Local usa un directorio temporal y promoción atómica. En Drive, `assessment` publica únicamente `ficha_oportunidad.pdf`, sin crear una carpeta `output` ni un manifiesto remoto; `detailed-analysis` conserva la carpeta temporal y promociona su catálogo completo. `storageQuotaExceeded` se traduce a una recomendación explícita de Shared Drive.

El catálogo cerrado de `detailed-analysis` contiene `resumen_tecnico.docx` (contexto completo para técnico, arquitecto o revisor), `guia_preparacion_oferta.docx` (guía operativa para bid manager o redactor), `propuesta_tecnica_base.docx` y `simulador_economico.xlsx`. Los dos primeros se generan de forma determinista desde `dossier.json`; `summary` conserva su ID histórico, aunque ahora identifica la guía de preparación.

La salida del análisis y de todos los entregables es siempre española. Las
citas de evidencia, identificadores, nombres de archivo, referencias estables o
de página, nombres propios y fórmulas literales designadas por el schema se
mantienen textualmente como material fuente. En la propuesta técnica,
`output_language` solo acepta `auto` o `es`; el valor heredado `en` se rechaza
para impedir una salida parcial en inglés.

La verificación de evidencias conserva documento y página estrictos. Tolera solamente espacios artificiales introducidos por el layout PDF y registra `verification_method` (`exact` o `layout_whitespace`). Una cita no comprobable produce un informe parcial con advertencias; los fallos estructurales o semánticos continúan siendo bloqueantes.

Consulta el README para autenticación y comandos. Las salidas quedan en el destino indicado y los runs/diagnósticos bajo `runs/`. Antes de cerrar cambios ejecuta pytest, `docker compose config --quiet` y `docker compose build`. Las llamadas reales a Drive requieren autorización explícita; los tests usan fakes.
