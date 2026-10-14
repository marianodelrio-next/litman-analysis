# Desarrollo local desde checkout

Esta guía es para contribuir desde el checkout. Requiere Python 3.11, `uv` y
autenticación explícita de Codex:

```sh
uv sync
cd deployment
uv run litman-core run
uv run pytest -q
```

La CLI local ejecuta `JobRunner` directamente desde el código del checkout.
Para consumir una wheel instalada sin checkout, consulta
[`deployment/local-install`](../local-install/README.md).
