# Desarrollo local desde checkout

Esta guía es para contribuir desde el checkout. Requiere Python 3.11, `uv` y
la autenticación de Codex o, en Ubuntu, de Claude Code
(`LITMAN_CORE_LLM_PROVIDER=claude-code`).

Desde la raíz del repositorio:

```sh
uv sync
uv run pytest -q
cp deployment/config_example.toml deployment/config.toml
cd deployment
uv run litman-core run
```

La CLI local ejecuta `JobRunner` directamente desde el código del checkout.
Para consumir una wheel instalada sin checkout, consulta
[`deployment/local-install`](../local-install/README.md).
