# Mapa del código

Usa este índice para localizar la propiedad de un cambio y comprueba el código
actual antes de editarlo.

| Área | Rutas | Propósito de navegación |
| --- | --- | --- |
| Documentación y tooling transversal | `README.md`, `AGENTS.md`, `docs/`, `.codex/`, `.agents/`, `.factory/changes/` | Visión de los dos paquetes, contrato público entre ellos y reglas de desarrollo. No forman parte del runtime de producto. |
| Contrato CLI versionado | `docs/contracts.md`, `docs/contracts/` (`core-result.schema.json`, `core-info.schema.json`, `core-config.minimal.toml`, `examples/`) | Fuente única del contrato `litman-core run`/`info`: esquemas, ejemplos y plantilla mínima que usa el harness. |
| Distribución Core | `core/pyproject.toml`, `core/uv.lock`, `core/README.md` | Paquete `litman-core`, dependencias y entrada de desarrollo. |
| Ejecución y contrato de Core | `core/src/litman_core/cli.py`, `core/src/litman_core/errors.py`, `core/src/litman_core/execution/job_runner.py`, `core/src/litman_core/application/` | CLI `litman-core` (JSON único y `info`), códigos de error cerrados (`CoreError`), carga de jobs y orquestación local de análisis. |
| Dominio, pipelines y generación de Core | `core/src/litman_core/domain/`, `pipelines/`, `generation/`, `resources/` | Modelo de jobs, análisis, validación y artefactos versionados. |
| Infraestructura de Core | `core/src/litman_core/infrastructure/` | Documentos, almacenamiento, metadatos de ejecución y proveedores LLM. |
| Despliegue y pruebas de Core | `core/deployment/`, `core/tests/`, `core/docs/` | Guías operativas y Docker opcional, pruebas y documentación interna de Core. |
| Distribución Harness | `harness/pyproject.toml`, `harness/uv.lock`, `harness/README.md` | Paquete `litman-harness`, que declara Core como dependencia de distribución. |
| Interfaces y ejecución de Core desde Harness | `harness/src/litman_harness/interfaces/`, `harness/src/litman_harness/adapters/core.py` | CLI `litman`, MCP `litman-mcp` y ejecución de `litman-core run --config` como proceso. |
| Expediente y análisis del Harness | `harness/src/litman_harness/{dossier,analysis,plans,adapters}/` | Estado del expediente, planes locales, Drive con OAuth personal y publicación de resultados. |
| Producto, despliegue y pruebas del Harness | `harness/agent/` (skills, subagente y `agent/workspace/` con la plantilla de `LitMan/AGENTS.md`), `harness/src/litman_harness/installation.py`, `harness/deployment/` (`install.sh`/`install.ps1`/`uninstall.sh`/`uninstall.ps1` y la instalación avanzada con wheels), `harness/tests/`, `harness/docs/` | Recursos del agente de producto, instalación guiada para personas sin IT (`litman install`/`uninstall`, scripts), pruebas y documentación interna del harness. |

El contrato entre las distribuciones se describe en [contracts.md](contracts.md).
Para las arquitecturas internas, consulta la documentación de
[Core](../core/docs/) o del [Harness](../harness/docs/development.md).
