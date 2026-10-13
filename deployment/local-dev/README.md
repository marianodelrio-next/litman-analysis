# Desarrollo local desde checkout

Esta guía es para contribuir desde el checkout. Requiere Python 3.11, `uv` y
autenticación explícita de Codex:

```sh
uv sync
uv run litman-core assess ./local-data/input --output ./local-data/output
uv run litman-core analyze ./local-data/input --output ./local-data/output
uv run litman-core run ./job.json
UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q
```

La CLI local ejecuta `JobRunner` directamente desde el código del checkout.
Para consumir una wheel instalada sin checkout, consulta
[`deployment/local-install`](../local-install/README.md).
