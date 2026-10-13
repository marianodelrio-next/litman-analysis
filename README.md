# LitMan Core

LitMan Core es un servicio Python 3.11 que analiza expedientes de contratación.
El repositorio ofrece desarrollo desde checkout (`deployment/local-dev/`),
consumo de una wheel (`deployment/local-install/`) y Docker como distribución
aislada opcional (`deployment/docker/`).

Admite jobs `assessment` y `detailed-analysis`, con entrada y salida local o Google Drive. Drive requiere credenciales explícitas; los tests usan dobles y no acceden a servicios externos.

## Desarrollo local

Requisitos: Python 3.11+, `uv`, Codex CLI y autenticación de Codex configurada.

```bash
uv sync
uv run litman-core assess ./local-data/input --output ./local-data/output
uv run litman-core analyze ./local-data/input --output ./local-data/output
uv run litman-core run ./job.json
```

`assess` y `analyze` son atajos para jobs locales. `run` carga un job JSON o YAML y permite configurar local o Drive en cada extremo. La CLI no conoce Docker, no traduce rutas del host y no acepta `--native`.

Para instalar una wheel sin checkout, sigue [`deployment/local-install`](deployment/local-install/README.md).

El empaquetado de release produce la wheel con `uv build --wheel`; construirla
no equivale a ejecutar el servicio desde una instalación local.

Cada publicación crea una carpeta versionada `<job_id>-<timestamp UTC>`. Ambos destinos usan el mismo catálogo público: assessment contiene únicamente `ficha_oportunidad.pdf`; detailed-analysis contiene `resumen_tecnico.docx`, `guia_preparacion_oferta.docx`, el único DOCX técnico declarado por el manifiesto y `simulador_economico.xlsx`. Runs, logs, resultados JSON, lineage, manifiestos de generación y manifiestos de publicación son internos y no se publican.

## Docker opcional

Desde la raíz del repositorio:

```bash
docker compose -f deployment/docker/compose.yaml config --quiet
docker compose -f deployment/docker/compose.yaml build
docker compose -f deployment/docker/compose.yaml run --rm litman-core assess /input --output /output
```

Docker construye una wheel y la instala en la imagen final; no usa las fuentes
del checkout como runtime. Compose monta el job en `/job`, la entrada en
`/input`, la salida en `/output`, los runs en `/data/runs`, secretos en
`/run/secrets` y el estado de Codex en `/var/lib/litman-core/codex`. Los jobs
ejecutados en Docker deben usar esas rutas internas; no existe traducción
automática host→contenedor. La imagen usa el entrypoint `litman-core`, usuario
no root, filesystem de solo lectura, capabilities eliminadas y
`no-new-privileges`.

Las comprobaciones de seguridad o preflight pertenecen al despliegue Docker, no al contrato de `litman_core`. No se deben incluir credenciales en jobs, logs, prompts ni en el contexto de build.

## Desarrollo

```bash
UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q
docker compose -f deployment/docker/compose.yaml config --quiet
```

La suite no usa credenciales reales ni publica en Google Drive.
