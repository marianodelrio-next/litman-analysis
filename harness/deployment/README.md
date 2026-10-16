# Instalación del harness

Para producción, construya u obtenga wheels compatibles de `litman-core` y
`litman-harness`, y póngalas fuera del checkout:

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python /ruta/litman_core-0.1.0-py3-none-any.whl /ruta/litman_harness-0.1.0-py3-none-any.whl
.venv/bin/litman diagnose
.venv/bin/litman-mcp
```

No use el `uv.lock` de desarrollo para una instalación de release: su fuente
local `../core` sólo sirve al checkout. Configure OAuth y los directorios de
estado fuera del clon; el harness localiza `litman-core` junto a su intérprete.
