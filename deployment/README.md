# Operación de LitMan Core

`config.toml` es el único contrato operativo. Ejecute desde este directorio:

Para preparar una configuración local, copie [`config_example.toml`](config_example.toml)
a `config.toml` y ajuste sus rutas o IDs. `config.toml` es local y no se versiona.

```sh
litman-core run
litman-core run --config /ruta/config.toml --env-file /ruta/.env
```

Las rutas locales se resuelven respecto al TOML. `[output].directory` siempre
recibe la carpeta final `<job.id>-<timestamp UTC>`; `google_drive_folder_id`
añade una réplica Drive. `.env` solo contiene autenticación y rutas a
`local-secrets/`; nunca se copia a un run. El entorno heredado prevalece sobre
`.env`. `include_run_files = false` (por defecto) conserva solo los entregables;
`true` conserva y replica el árbol completo del run. Los fallos conservan ese
árbol local y no promueven una carpeta final en Drive.

Use `type = "assessment"` para generar `ficha_oportunidad.pdf`; para
`detailed-analysis` se generan siempre los cuatro entregables. No se admiten
jobs JSON/YAML, `assess`, `analyze`, `check` ni `.local-state`.

Las guías de [desarrollo local](local-dev/README.md),
[instalación wheel](local-install/README.md) y [Docker](docker/README.md)
contienen sus requisitos e invocación específicos.
