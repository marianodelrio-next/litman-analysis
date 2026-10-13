# LitMan Core

LitMan Core es un servicio Python 3.11 que analiza expedientes de contratación.
La configuración, autenticación y despliegue se documentan en
[deployment/README.md](deployment/README.md).

Admite jobs `assessment` y `detailed-analysis`, con entrada y salida local o Google Drive. Drive requiere credenciales explícitas; los tests usan dobles y no acceden a servicios externos.

## Desarrollo local

Requisitos: Python 3.11+, `uv`, Codex CLI y autenticación de Codex configurada.

```bash
uv sync
cd deployment
uv run litman-core run
```

`run` carga `config.toml` y su `.env` adyacente. La CLI no conoce Docker ni
traduce rutas del host.

Para instalar una wheel sin checkout, sigue [`deployment/local-install`](deployment/local-install/README.md).

El empaquetado de release produce la wheel con `uv build --wheel`; construirla
no equivale a ejecutar el servicio desde una instalación local.

Cada publicación crea una carpeta versionada `<job_id>-<timestamp UTC>`. Ambos destinos usan el mismo catálogo público: assessment contiene únicamente `ficha_oportunidad.pdf`; detailed-analysis contiene `resumen_tecnico.docx`, `guia_preparacion_oferta.docx`, el único DOCX técnico declarado por el manifiesto y `simulador_economico.xlsx`. Runs, logs, resultados JSON, lineage, manifiestos de generación y manifiestos de publicación son internos y no se publican.

## Docker opcional

Desde la raíz del repositorio:

```bash
docker compose -f deployment/docker/compose.yaml config --quiet
docker compose -f deployment/docker/compose.yaml build
docker compose -f deployment/docker/compose.yaml run --rm litman-core run
```

Docker construye una wheel y la instala en la imagen final; no usa las fuentes
del checkout como runtime. Compose monta `config.toml` en `/app/config.toml`,
la entrada en `/app/input`, los resultados en `/app/runs`, secretos en
`/run/secrets` y el estado de Codex en `/var/lib/litman-core/codex`. No existe
traducción automática host→contenedor. La imagen usa el entrypoint `litman-core`, usuario
no root, filesystem de solo lectura, capabilities eliminadas y
`no-new-privileges`.

Las comprobaciones de seguridad o preflight pertenecen al despliegue Docker, no al contrato de `litman_core`. No se deben incluir credenciales en jobs, logs, prompts ni en el contexto de build.

## Desarrollo

```bash
UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q
docker compose -f deployment/docker/compose.yaml config --quiet
```

La suite no usa credenciales reales ni publica en Google Drive.
