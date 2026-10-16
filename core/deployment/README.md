# Operación de LitMan Core

`config.toml` es el único contrato operativo. `input.kind` e
`input.location` definen el origen; `output.directory` define la raíz local de
los runs y `output.google_drive_folder_id` configura una réplica Drive.
Ejecute desde este directorio:

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
`detailed-analysis` se generan siempre los cuatro entregables con la plantilla
aprobada (`technical_document` y `economic_simulator`); no existe una clave
pública `[analysis]` para configurarla: se rechaza como desconocida. `[llm]
provider` (`codex`, por defecto, o `claude-code`) y `model` opcional eligen el
proveedor y modelo del análisis; ver el contrato completo en
[`../../docs/contracts.md`](../../docs/contracts.md).

Las guías de [desarrollo local](local-dev/README.md),
[instalación wheel](local-install/README.md) y [Docker](docker/README.md)
contienen sus requisitos e invocación específicos.
