# Docker opcional

Docker ejecuta la misma CLI instalada en la imagen. Desde la raíz:

Prepare antes `deployment/config.toml` copiando `deployment/config_example.toml`;
el archivo operativo puede contener rutas o IDs locales y no se versiona.

```sh
docker compose -f deployment/docker/compose.yaml build
docker compose -f deployment/docker/compose.yaml run --rm litman-core run
```

Compose carga `deployment/config.toml` como `/app/config.toml`, `deployment/input/`
como `/app/input` y escribe en `deployment/runs/` (`/app/runs`). Por defecto,
`local-secrets/` se resuelve relativo a `deployment/docker/`, por lo que apunta a
`deployment/local-secrets/`; se puede reemplazar con `LITMAN_CORE_SECRETS_DIR`.
El subdirectorio `local-secrets/codex` se monta separadamente para el estado
ChatGPT. Ejecuta siempre `run`, sin job JSON/YAML ni argumentos de entrada/salida.
