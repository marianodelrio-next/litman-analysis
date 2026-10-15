# Desarrollo del harness de expediente

`harness/` es una distribución local separada de `litman_core`. Sus adaptadores
CLI (`litman`) y MCP stdio (`litman-mcp`) comparten operaciones de negocio y
respuestas JSON; no aceptan claves de cuenta de servicio ni tokens en argumentos
o por stdio.

El adaptador configurado hoy para CLI/MCP es `LITMAN_HARNESS_METADATA`: un JSON
local de metadatos no secretos, estrictamente de lectura, útil para desarrollo y
para comprobar que ambos transportes comparten `identity`, `inspect` y `status`.
No es un sustituto de OAuth ni habilita descargas, análisis o mutaciones.

En esta entrega se pueden probar con dobles las consultas, planes y la ejecución
local de Core. Las mutaciones de incorporación requieren que una persona acepte
el `plan_id` exacto. No obstante, mientras falte un smoke autorizado que
demuestre una precondición atómica de Drive, incluso un plan aceptado devuelve
`pending_concurrency_gate` **sin escribir nada**: no crea carpetas, manifiesto ni
`contexto.md`, y nunca afirma que el estado compartido se haya publicado.

Antes de descargar y justo antes de lanzar Core, el harness vuelve a comprobar
que cada original pertenece a la raíz y unidad del expediente, no está en
papelera y permite descarga. Solo acepta los proveedores `codex` y
`claude-code`; valida `validation.json` y el catálogo público exacto antes de
devolver un resultado local validado. Si Core falla, el workspace privado se
conserva y su ruta aparece en el error para diagnóstico; tras éxito se limpia.

Para un smoke manual de transporte MCP, tras instalar el paquete en un entorno
de desarrollo, ejecute `litman-mcp` y envíe una petición JSON-RPC `tools/list`.
Debe listar las operaciones sin solicitar ni imprimir credenciales. La conexión
OAuth corporativa, su carpeta de prueba y la verificación de `drive.file` con dos
cuentas necesitan autorización explícita y pertenecen a la puerta de cierre.

Por tanto, todavía no están satisfechos los criterios de aceptación que exigen
una segunda instalación OAuth real, capacidades reales de dos cuentas y
`drive.file`, publicación de análisis en Drive, conversión única de una oferta
viva, ni escritura concurrentemente segura de `manifest.json`/`contexto.md`.
