# Instalación local de una wheel

Esta guía consume una distribución construida de `litman-core`, sin ejecutar
el código desde un checkout. Requiere Python 3.11, `uv` y autenticación de
Codex configurada por el usuario.

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

Las rutas relativas del TOML se resuelven respecto al propio archivo. El
workspace temporal de LitMan usa `/tmp/litman-core` por defecto y se elimina al
terminar la ejecución. El contrato usa `input.kind`/`input.location`,
`output.directory` y opcionalmente `output.google_drive_folder_id`;
`publication.include_run_files` controla si se conserva el árbol completo del
run. Para `detailed-analysis`, la generación se configura bajo
`analysis.detailed.generation`. Configura la autenticación de Codex y, si usas
Drive, `GOOGLE_APPLICATION_CREDENTIALS` según tu entorno; esta guía no crea
credenciales ni instaladores.

Para Claude Code en Ubuntu, autentícate previamente con `claude`, configura
`LITMAN_CORE_LLM_PROVIDER=claude-code` y, opcionalmente,
`LITMAN_CORE_CLAUDE_CONFIG_DIR` (Core lo reenvía internamente como
`CLAUDE_CONFIG_DIR`).
LitMan nunca copia ni inspecciona tokens. El smoke autenticado de Codex/Claude
queda pendiente de ejecutarse manualmente en una terminal del usuario.
