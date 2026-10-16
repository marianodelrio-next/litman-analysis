# Arquitectura transversal

LitMan se compone de dos distribuciones Python 3.11 hermanas y de tooling de
desarrollo en la raíz. Cada distribución tiene su propio proyecto, lock,
entorno, documentación, pruebas y despliegue.

`litman-core` vive en `core/` y analiza licitaciones. Su interfaz pública es la
CLI `litman-core`. `litman-harness` vive en `harness/`, administra el expediente
con OAuth personal y expone las interfaces `litman` y `litman-mcp`. El harness
declara Core como dependencia de distribución, pero no importa sus módulos: lo
ejecuta mediante `litman-core run --config` y consume el resultado público de
ese proceso. Los detalles de ese límite están en el
[contrato compartido](contracts.md).

```text
Usuario o agente de producto
        |
        v
litman / litman-mcp  (harness/)
        |
        | proceso: litman-core run --config
        v
litman-core          (core/)
```

Core puede instalarse y ejecutarse por sí solo. El harness requiere una
instalación compatible de Core, tanto en desarrollo como al instalar las dos
wheels. Docker es una opción de despliegue exclusiva de Core; el harness no
forma parte de esa imagen.

La raíz contiene la visión del repositorio, este documento, el contrato
compartido, el mapa de código y configuración de desarrollo (`.codex/` y
`.agents/`). Ese tooling no es runtime de producto. La arquitectura y las
decisiones internas de cada paquete se mantienen junto a su propietario:

- [Core: operaciones y documentación](../core/docs/operations.md)
- [Harness: desarrollo](../harness/docs/development.md)
