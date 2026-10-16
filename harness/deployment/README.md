# Instalación de LitMan

## Para una persona de negocio (recomendado)

Pensado para alguien sin IT que ya tiene instalada Codex App o Claude
Desktop, y Git. Pegue una sola frase en una terminal; el script es
idempotente y sirve también para actualizar.

| Elemento | Windows | Ubuntu |
| --- | --- | --- |
| Carpeta LitMan que se abre en la app (`AGENTS.md`; en Claude también `CLAUDE.md` con `@AGENTS.md`, porque Claude Desktop no lee `AGENTS.md`) | `%USERPROFILE%\LitMan` | `~/LitMan` |
| Código del repo, oculto, nunca se abre | `%LOCALAPPDATA%\LitMan\src` | `~/.local/share/litman/src` |
| `litman`, `litman-mcp`, `litman-core` | herramienta de uv (Python 3.11 gestionado por uv) | igual |
| Skills (`conectar-licitacion`, `resumir-licitacion`, `preparar-equipo`) | Codex: `~/.agents/skills` · Claude: `~/.claude/skills` | igual |
| Subagente `lector-licitacion` | `~/.codex/agents/*.toml` · `~/.claude/agents/*.md` | igual |
| MCP `litman` (ruta absoluta, timeout 2 h) | bloque delimitado en `~/.codex/config.toml` · `~/.claude.json` (`--scope user`) | igual |
| Cliente OAuth, token, ajustes, estado, manifiesto de instalación | `%LOCALAPPDATA%\litman-harness` | `~/.config` y `~/.local/state/litman-harness` |

```sh
LITMAN_APP=codex bash -c "$(curl -fsSL https://raw.githubusercontent.com/marianodelrio-next/litman-analysis/master/harness/deployment/install.sh)"
```

```powershell
$env:LITMAN_APP='codex'; irm https://raw.githubusercontent.com/marianodelrio-next/litman-analysis/master/harness/deployment/install.ps1 | iex
```

(`LITMAN_APP` vale `codex` o `claude`, según la app que use.)

El script sólo hace lo estrictamente necesario para LitMan: clona o
actualiza el repositorio, instala las herramientas con
`uv tool install --python 3.11 harness --with core`, y ejecuta
`litman install --app <app> --source <repo>`, que crea la carpeta LitMan,
copia skills y subagente, registra el servidor MCP (con
`tool_timeout_sec = 7200` en Codex, `MCP_TOOL_TIMEOUT` en Claude Code) y
guarda un manifiesto de lo instalado. **Nunca instala Git, uv, la CLI del
proveedor ni un navegador por su cuenta**: si falta algo, se detiene con el
enlace oficial o el comando de un solo paso, y la persona lo ejecuta ella
misma antes de volver a pegar la frase.

Al terminar: cierre y reabra la app, abra la carpeta `LitMan` y escriba
**"prepara mi equipo"**; la skill homónima guía el resto (cliente OAuth de
Drive vía `litman install --oauth-client`, `litman login`, sesión del
proveedor LLM, `setup`).

### Mantenimiento

- **Actualizar**: vuelva a pegar la misma frase de instalación y reinicie la
  app.
- **Reparar**: dentro de la app, escriba "prepara mi equipo" de nuevo
  (ejecuta `diagnose` y resuelve sólo lo que falte).
- **Desinstalar**: ejecute el script correspondiente.
  ```sh
  bash harness/deployment/uninstall.sh
  ```
  ```powershell
  harness/deployment/uninstall.ps1
  ```
  Por defecto borra únicamente lo que registró `litman install` (skills,
  subagente, bloque/registro MCP); conserva el token, el cliente OAuth y la
  carpeta `LitMan`. Para ampliarlo:
  - `LITMAN_REMOVE_WORKSPACE=1`: también borra la carpeta `LitMan` (sólo si
    la creó la instalación).
  - `LITMAN_PURGE_DATA=1`: también borra el token, el cliente OAuth, los
    ajustes locales, los planes y el directorio de trabajo.
  Nunca desinstala Git, uv, la CLI del proveedor ni un navegador.

### `litman install` / `litman uninstall` (lo que ejecutan los scripts)

```sh
litman install --app codex --source /ruta/al/repo    # crea o actualiza
litman install --oauth-client /ruta/client_secret.json [--delete-original]
litman uninstall [--remove-workspace] [--purge-data]
```

Son operaciones sólo-CLI (como `litman login`): no aparecen en
`tools/list` del MCP. Ver `harness/src/litman_harness/installation.py` para
el detalle de idempotencia, detección de conflictos y el manifiesto.

## Instalación avanzada (wheels, para quien ya opera un entorno Python)

Para un entorno controlado por IT, sin el instalador guiado: construya u
obtenga wheels compatibles de `litman-core` y `litman-harness`, y póngalas
fuera del checkout.

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python /ruta/litman_core-0.1.0-py3-none-any.whl /ruta/litman_harness-0.1.0-py3-none-any.whl
.venv/bin/litman setup --json '{"provider": "codex"}'
.venv/bin/litman diagnose
.venv/bin/litman-mcp
```

No use el `uv.lock` de desarrollo para una instalación de release: su fuente
local `../core` sólo sirve al checkout. Configure OAuth y los directorios de
estado fuera del clon; el harness localiza `litman-core` en la carpeta de
scripts del entorno activo (`sysconfig.get_path("scripts")`), no junto al
intérprete resuelto. `litman setup` comprueba `litman-core info` y guarda el
proveedor (y modelo opcional) elegido para esta instalación antes de
analizar cualquier licitación; ver el contrato en
[`docs/contracts.md`](../../docs/contracts.md).

El harness nunca lee ni escribe el `config.toml` de LitMan Core: genera su
propia configuración mínima en memoria para cada análisis (tipo de job,
carpeta de entrada temporal, carpeta de salida temporal y el proveedor fijado
por `setup`) y la pasa a `litman-core run --config`. No es necesario preparar
`config.toml`/`local-secrets/` de Core para usar el harness; esos archivos
sólo aplican al uso independiente de Core descrito en
[`core/deployment/README.md`](../../core/deployment/README.md).

Los resultados publicados no quedan en el disco local: `apply_publication`
los sube a la carpeta Drive conectada, dentro de una carpeta con fecha
(`AAAA-MM-DD <publication_id>`) bajo `Analisis inicial` o `Analisis
detallado`, según el tipo de análisis.
