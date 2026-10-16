# Contrato compartido Core–Harness

El harness crea un `config.toml` local y ejecuta `litman-core run --config
RUTA`. No importa módulos internos de Core ni usa su publicador de cuenta de
servicio: siempre establece `publication.include_run_files = false` y omite
`output.google_drive_folder_id`.

En éxito, Core escribe en stdout un JSON con `status: "succeeded"`,
`publication_id`, `local_path` y el catálogo público `artifacts` con `name`,
`uri` y `checksum`. En fallo sale con código distinto de cero. El harness
valida esos campos antes de publicar los resultados en Drive.
