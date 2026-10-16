# LitMan Core

LitMan Core es un servicio Python 3.11 que analiza expedientes de contratación.
La configuración, autenticación y despliegue se documentan en
[deployment/README.md](deployment/README.md). El contrato compartido con el
harness está en [../docs/contracts.md](../docs/contracts.md).

Admite jobs `assessment` y `detailed-analysis`, con entrada y salida local o Google Drive. Drive requiere credenciales explícitas; los tests usan dobles y no acceden a servicios externos.

## Desarrollo local

Requisitos: Python 3.11+, `uv`, Codex CLI y autenticación de Codex configurada
(ejecuta `codex login` una vez en tu cuenta; Core lee la sesión guardada en
`CODEX_HOME/auth.json`, por defecto `~/.codex/auth.json`, con permisos
`0600`).

En Ubuntu también puede usarse la sesión local de Claude Code sin guardar
tokens en LitMan: use `[llm] provider = "claude-code"` en `config.toml` (el
proveedor y el modelo sólo se eligen ahí; no hay variables de entorno para
elegirlos). Codex es el valor predeterminado. Claude se ejecuta en modo no
interactivo y sólo con lectura del workspace privado. Windows, Docker con
Claude y cancelación explícita quedan fuera de alcance.

```bash
cd core
uv sync
cd deployment
uv run litman-core run
```

`run` carga `config.toml` y su `.env` adyacente. La CLI no conoce Docker ni
traduce rutas del host.

El repositorio incluye `deployment/config_example.toml` como plantilla. Copie
esa plantilla a `deployment/config.toml` antes de ejecutar; la configuración
operativa queda ignorada por Git.

Para instalar una wheel sin checkout, sigue [`deployment/local-install`](deployment/local-install/README.md).

El empaquetado de release produce la wheel con `uv build --wheel`; construirla
no equivale a ejecutar el servicio desde una instalación local.

Cada publicación crea una carpeta versionada `<job_id>-<YYYYMMDDTHHMMSS.ffffffZ>`. Ambos destinos usan el mismo catálogo público: assessment contiene únicamente `ficha_oportunidad.pdf`; detailed-analysis contiene `resumen_tecnico.docx`, `guia_preparacion_oferta.docx`, el único DOCX técnico declarado por el manifiesto y `simulador_economico.xlsx`. El run conserva `input/`, `output/` y `logs/`; los archivos internos no forman parte del catálogo público.

## Docker opcional

Antes de construir, copia `deployment/config_example.toml` a
`deployment/config.toml` (igual que en desarrollo local) y, si vas a usar
Codex o Drive, prepara `deployment/local-secrets/` con las credenciales
correspondientes; ver [`deployment/docker`](deployment/docker/README.md) para
el detalle de esas rutas. Desde la raíz del repositorio (del monorepo, no de
`core/`):

```bash
docker compose -f core/deployment/docker/compose.yaml config --quiet
docker compose -f core/deployment/docker/compose.yaml build
docker compose -f core/deployment/docker/compose.yaml run --rm litman-core run
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
cd core && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q
docker compose -f core/deployment/docker/compose.yaml config --quiet
```

La suite no usa credenciales reales ni publica en Google Drive.
