# Ejecución local

Requiere Python 3.11, las dependencias del proyecto y autenticación explícita de Codex:

```sh
uv run litman-core assess ./local-data/input --output ./local-data/output
uv run litman-core analyze ./local-data/input --output ./local-data/output
uv run litman-core run ./job.json
```

Docker es opcional; la CLI local ejecuta `JobRunner` directamente.
