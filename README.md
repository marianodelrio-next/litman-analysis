# LitMan

LitMan se distribuye como dos paquetes Python 3.11 hermanos:

- [LitMan Core](core/README.md) analiza licitaciones localmente o, de forma opcional, en Docker.
- [LitMan Harness](harness/README.md) gestiona el expediente con OAuth personal y ejecuta Core mediante su CLI pública.

Cada paquete tiene su propio `pyproject.toml`, lock y entorno de desarrollo. El
contrato entre ambos está en [docs/contracts.md](docs/contracts.md); el mapa de
componentes está en [docs/codebase-map.md](docs/codebase-map.md).
