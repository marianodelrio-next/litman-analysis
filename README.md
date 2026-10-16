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
