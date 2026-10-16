# Desarrollo local desde checkout

Esta guía es para contribuir desde el checkout. Requiere Python 3.11, `uv` y
la autenticación de Codex (`codex login` una vez; Core lee la sesión en
`CODEX_HOME/auth.json`) o, en Ubuntu o Windows 10/11, de Claude Code (sesión `claude` ya
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
En Windows usa PowerShell o `cmd` para los comandos equivalentes; Core emplea
un workspace bajo el temporal del sistema y Claude requiere un `.exe` nativo.
Para consumir una wheel instalada sin checkout, consulta
[`deployment/local-install`](../local-install/README.md).
