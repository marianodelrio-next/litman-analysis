# LitMan Harness

El harness administra un expediente con OAuth personal y expone `litman` y
`litman-mcp`. Ejecuta Core únicamente mediante `litman-core`, instalado como
dependencia de distribución en el mismo entorno.

En Windows se usa el ejecutable instalado `litman-core.exe` junto al intérprete
del entorno; no se busca Core en `PATH`. El estado privado por defecto se
guarda bajo `%LOCALAPPDATA%/litman-harness` (los overrides `LITMAN_HARNESS_*`
y `XDG_*` explícitos conservan precedencia).

```sh
cd harness
uv sync
UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q
```

Consulta [docs/development.md](docs/development.md) para desarrollo y
[deployment/README.md](deployment/README.md) para instalar las dos wheels.
