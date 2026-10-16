# LitMan Harness

El harness administra un expediente con OAuth personal y expone `litman` y
`litman-mcp`. Ejecuta Core únicamente mediante `litman-core`, instalado como
dependencia de distribución en el mismo entorno.

```sh
cd harness
uv sync
UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q
```

Consulta [docs/development.md](docs/development.md) para desarrollo y
[deployment/README.md](deployment/README.md) para instalar las dos wheels.
