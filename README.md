# LitMan

LitMan se distribuye como dos paquetes Python 3.11 hermanos:

- [LitMan Core](core/README.md) analiza licitaciones localmente o, de forma opcional, en Docker.
- [LitMan Harness](harness/README.md) gestiona el expediente con OAuth personal y ejecuta Core mediante su CLI pública.

Cada paquete tiene su propio `pyproject.toml`, lock y entorno de desarrollo. El
contrato entre ambos está en [docs/contracts.md](docs/contracts.md); el mapa de
componentes está en [docs/codebase-map.md](docs/codebase-map.md).

## ¿Qué necesito instalar?

- **Solo quiero analizar un expediente puntual** (un PDF/carpeta local o en
  Drive, sin gestionar el ciclo de vida completo): instala y lanza únicamente
  LitMan Core; ver [core/README.md](core/README.md).
- **Quiero gestionar un expediente completo en Drive** (organizar originales,
  publicar análisis, resumen, oferta viva): instala LitMan Harness, que a su
  vez requiere LitMan Core instalado en el mismo entorno (el harness lo
  invoca con la configuración mínima necesaria, no con tu `config.toml` de
  Core); ver [harness/deployment/README.md](harness/deployment/README.md).
- **Quiero contribuir al código de ambos**: sigue la guía de desarrollo de
  cada paquete por separado (`core/README.md` y `harness/README.md`); cada
  uno tiene su propio checkout, `uv sync` y tests.

## Instalación para una persona de negocio (Codex App o Claude Desktop)

No hace falta saber de IT: sólo tener instalada la app (Codex o Claude
Desktop) y Git. Abra una terminal y pegue la frase de su sistema (cambie
`codex`/`claude` por la app que use):

- **Ubuntu/Linux:**
  ```sh
  LITMAN_APP=codex bash -c "$(curl -fsSL https://raw.githubusercontent.com/marianodelrio-next/litman-analysis/master/harness/deployment/install.sh)"
  ```
- **Windows (PowerShell):**
  ```powershell
  $env:LITMAN_APP='codex'; irm https://raw.githubusercontent.com/marianodelrio-next/litman-analysis/master/harness/deployment/install.ps1 | iex
  ```

El script clona el repositorio, instala `litman`/`litman-mcp`/`litman-core`,
registra las skills, el subagente y el servidor MCP en su app, y crea la
carpeta `LitMan` con las instrucciones de inicio. **Nunca instala Git, uv, la
CLI del proveedor (Codex o Claude Code) ni un navegador por su cuenta**: si
falta algo, se detiene y explica exactamente qué ejecutar o descargar; usted
lo hace y vuelve a pegar la misma frase.

Al terminar: cierre y reabra la app, abra la carpeta `LitMan` y escriba
**"prepara mi equipo"**; la skill `preparar-equipo` le guía por el resto
(cliente OAuth de Drive, inicio de sesión, proveedor de análisis).

- **Actualizar**: vuelva a pegar la misma frase y reinicie la app.
- **Reparar**: dentro de la app, escriba "prepara mi equipo" de nuevo.
- **Desinstalar**: ejecute `harness/deployment/uninstall.sh` (o
  `uninstall.ps1` en Windows); conserva por defecto el token, el cliente
  OAuth y la carpeta `LitMan`. Ver
  [harness/deployment/README.md](harness/deployment/README.md) para las
  variables que amplían la desinstalación.
