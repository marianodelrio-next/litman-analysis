# Desarrollo local desde checkout

Esta guía es para contribuir desde el checkout. Requiere Python 3.11, `uv` y
la autenticación de Codex (`codex login` una vez; Core lee la sesión en
`CODEX_HOME/auth.json`) o, en Ubuntu, de Claude Code (sesión `claude` ya
iniciada; `[llm] provider = "claude-code"` en `config.toml`; no hay variable
de entorno para elegir el proveedor).

Desde la raíz de `core/` (este `core/` del monorepo, no la raíz del
repositorio):

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
