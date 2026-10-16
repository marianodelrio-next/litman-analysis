# Instalación local de una wheel

Esta guía consume una distribución construida de `litman-core`, sin ejecutar
el código desde un checkout. Requiere Python 3.11, `uv` y autenticación de
Codex configurada por el usuario (`codex login` una vez; Core lee la sesión en
`CODEX_HOME/auth.json`, por defecto `~/.codex/auth.json`).

Construye u obtén una wheel como paso de empaquetado/release:

```sh
uv build --wheel --out-dir ./dist
```

En el directorio donde conservarás la instalación, crea un entorno e instala
la wheel concreta:

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python /ruta/a/litman_core-0.1.0-py3-none-any.whl
```

El único comando público de ejecución es:

```sh
.venv/bin/litman-core run
.venv/bin/litman-core run --config /ruta/a/config.toml
```

En Windows, las rutas equivalentes son `.venv\\Scripts\\python.exe` y
`.venv\\Scripts\\litman-core.exe`. El workspace temporal usa el directorio
temporal del sistema; `LITMAN_CORE_WORKSPACE_DIR` puede reemplazarlo.

Las rutas relativas del TOML se resuelven respecto al propio archivo. En POSIX,
el workspace temporal de LitMan usa `/tmp/litman-core` por defecto; en Windows
usa el directorio temporal del sistema más `litman-core`. Se elimina al terminar
la ejecución. El contrato de `config.toml` (claves obligatorias y
opcionales, valores por defecto) está en
[`../../../docs/contracts.md`](../../../docs/contracts.md); no hay superficie
pública para configurar plantillas de generación (`detailed-analysis` siempre
usa la plantilla aprobada). Configura la autenticación de Codex y, si usas
Drive, `GOOGLE_APPLICATION_CREDENTIALS` según tu entorno; esta guía no crea
credenciales ni instaladores.

Para Claude Code en Ubuntu o Windows, autentícate previamente con `claude`, usa
`[llm] provider = "claude-code"` en `config.toml` y, opcionalmente,
`LITMAN_CORE_CLAUDE_CONFIG_DIR` (variable de máquina; Core la reenvía
internamente como `CLAUDE_CONFIG_DIR`). El modelo por defecto de Claude Code es
`claude-sonnet-5`; para fijar otro usa `[llm] model` en el job. En Windows
configura `LITMAN_CORE_CLAUDE_BINARY` con el binario `.exe` nativo, no con un
lanzador `.cmd`/`.bat`.
LitMan nunca copia ni inspecciona tokens. El smoke autenticado de Codex/Claude
queda pendiente de ejecutarse manualmente en una terminal del usuario.
