# LitMan Core

LitMan Core es un servicio Python 3.11 que analiza expedientes de contratación. La CLI local ejecuta `JobRunner` directamente; Docker es una distribución opcional bajo `deployment/docker/` y ejecuta la misma CLI instalada.

Admite jobs `assessment` y `detailed-analysis`, con entrada y salida local o Google Drive. Drive requiere credenciales explícitas; los tests usan dobles y no acceden a servicios externos.

## Ejecución local

Requisitos: Python 3.11+, `uv`, Codex CLI y autenticación de Codex configurada.

```bash
uv sync
uv run litman-core assess ./local-data/input --output ./local-data/output
uv run litman-core analyze ./local-data/input --output ./local-data/output
uv run litman-core run ./job.json
```

`assess` y `analyze` son atajos para jobs locales. `run` carga un job JSON o YAML y permite configurar local o Drive en cada extremo. La CLI no conoce Docker, no traduce rutas del host y no acepta `--native`.

Cada publicación crea una carpeta versionada `<job_id>-<timestamp UTC>`. Ambos destinos usan el mismo catálogo público: assessment contiene únicamente `ficha_oportunidad.pdf`; detailed-analysis contiene `resumen_tecnico.docx`, `guia_preparacion_oferta.docx`, el único DOCX técnico declarado por el manifiesto y `simulador_economico.xlsx`. Runs, logs, resultados JSON, lineage, manifiestos de generación y manifiestos de publicación son internos y no se publican.

## Docker opcional

Desde la raíz del repositorio:

```bash
docker compose -f deployment/docker/compose.yaml config --quiet
docker compose -f deployment/docker/compose.yaml build
docker compose -f deployment/docker/compose.yaml run --rm litman-analysis assess /input --output /output
```

Compose monta el job en `/job`, la entrada en `/input`, la salida en `/output`, los runs en `/data/runs`, secretos en `/run/secrets` y el estado de Codex en `/var/lib/litman-analysis/codex`. Los jobs ejecutados en Docker deben usar esas rutas internas; no existe traducción automática host→contenedor. La imagen usa el entrypoint `litman-core`, usuario no root, filesystem de solo lectura, capabilities eliminadas y `no-new-privileges`.

Las comprobaciones de seguridad o preflight pertenecen al despliegue Docker, no al contrato de `litman_core`. No se deben incluir credenciales en jobs, logs, prompts ni en el contexto de build.

## Desarrollo

```bash
UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q
docker compose -f deployment/docker/compose.yaml config --quiet
```

La suite no usa credenciales reales ni publica en Google Drive.
