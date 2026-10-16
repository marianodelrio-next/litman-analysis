# Instalación del harness

Para producción, construya u obtenga wheels compatibles de `litman-core` y
`litman-harness`, y póngalas fuera del checkout:

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python /ruta/litman_core-0.1.0-py3-none-any.whl /ruta/litman_harness-0.1.0-py3-none-any.whl
.venv/bin/litman setup --json '{"provider": "codex"}'
.venv/bin/litman diagnose
.venv/bin/litman-mcp
```

No use el `uv.lock` de desarrollo para una instalación de release: su fuente
local `../core` sólo sirve al checkout. Configure OAuth y los directorios de
estado fuera del clon; el harness localiza `litman-core` junto a su intérprete.
`litman setup` comprueba `litman-core info` y guarda el proveedor (y modelo
opcional) elegido para esta instalación antes de analizar cualquier
licitación; ver el contrato en [`docs/contracts.md`](../../docs/contracts.md).

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
