# LitMan Analysis

LitMan Analysis ejecuta cada job completo en un único contenedor: materializa un expediente local o de Google Drive, normaliza sus documentos, ejecuta Codex, valida el resultado y lo publica en local o Drive.

Se admiten `assessment` y `detailed-analysis` con las cuatro rutas: local→local, local→Drive, Drive→local y Drive→Drive.

## Preparación

Requisitos: Python 3.11+, `uv`, Docker Compose y autenticación de Codex.

```bash
uv sync
cp .env.example .env
mkdir -p local-data/input local-data/output runs local-secrets .local-state/codex
install -m 600 ~/.codex/auth.json .local-state/codex/auth.json
docker compose build
docker compose run --rm --entrypoint codex litman-analysis login status
```

Para API key, guarda la clave en un archivo con permisos restringidos dentro de `local-secrets`, configura el modo `api-key` y la ruta interna del archivo. Para Drive, coloca la cuenta de servicio en `local-secrets/google-service-account.json` y comparte con su correo las carpetas de origen/destino; en el destino necesita permiso de editor o administrador de contenido. No incluyas secretos en jobs, logs, prompts ni en el contexto de construcción.

## Ejecución

Los jobs públicos conservan rutas del host. El launcher las traduce a `/input` y `/output`, monta únicamente esas rutas y ejecuta exactamente:

```bash
uv run litman-analysis run examples/jobs/assessment.local.json
# llamada resultante:
docker compose run --rm litman-analysis run /job/job.json
```

También siguen disponibles:

```bash
uv run litman-analysis assess ./local-data/input --output ./local-data/output
uv run litman-analysis analyze ./local-data/input --output ./local-data/output
```

Los wrappers `assess` y `analyze` son atajos local→local. Para cualquier ruta con Drive usa `run` y un job de `examples/jobs/`; `location` es una ruta del host cuando `kind` es `local` y el ID de una carpeta cuando es `google-drive`.

En una salida Google Drive, `assessment` crea dentro de `output.location` una carpeta con el `job_id` y publica en ella exclusivamente `ficha_oportunidad.pdf`; no crea una carpeta `output` ni un manifiesto remoto. La publicación Drive de `detailed-analysis` conserva su carpeta por job y su catálogo completo. La publicación local no cambia.

Un análisis detallado completo publica cuatro entregables: `resumen_tecnico.docx` para la revisión técnica del expediente, `guia_preparacion_oferta.docx` para coordinar la preparación de la oferta, `propuesta_tecnica_base.docx` y `simulador_economico.xlsx`. La generación completa usa los artefactos `technical-summary`, `summary`, `technical-document` y `economic-simulator`, en ese orden.

El contenedor monta el job en `/job` (solo lectura), la entrada en `/input` (solo lectura), la salida en `/output`, los runs en `/data/runs`, las credenciales en `/run/secrets` (solo lectura) y el estado Codex persistente en `/var/lib/litman-analysis/codex`. Codex comparte el contenedor y puede ver el mount de secretos; ningún prompt le solicita leerlo. El workspace efímero vive en `/tmp/litman-analysis` y se elimina siempre. Los runs y diagnósticos se conservan aunque falle el análisis.

Las citas se verifican primero literalmente y, para PDFs, con una segunda comparación que ignora únicamente espacios de maquetación. Las evidencias no verificables quedan señaladas como advertencias en el informe; los errores estructurales, referencias a documentos inexistentes y errores semánticos siguen impidiendo la publicación.

Preflights (el primero verifica el contrato externo del contenedor; el segundo además ejecuta Codex contra el fixture):

```bash
docker compose run --rm litman-analysis preflight runtime
LITMAN_ANALYSIS_INPUT_DIR=./tests/fixtures/codex-workspace docker compose run --rm litman-analysis preflight container
```

Bubblewrap no se instala ni se utiliza. Codex se invoca con
`--dangerously-bypass-approvals-and-sandbox`: el contenedor es la frontera de
aislamiento. Por ello Codex comparte el filesystem, la red y los secretos que
estén disponibles dentro del contenedor. Es una decisión aceptada para esta
herramienta interna; los mounts no deben contener información ajena al job y
nunca deben introducirse secretos en jobs, prompts, logs ni artefactos. El
contenedor sigue ejecutándose como usuario no root, sin capabilities, con raíz
de solo lectura y `no-new-privileges`.

## Desarrollo

```bash
UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q
docker compose config --quiet
docker compose build
```

Los tests de Drive usan dobles y no realizan publicaciones externas.
