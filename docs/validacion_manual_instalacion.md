# Validación manual de instalación y distribución

Lista de comprobaciones que no se pueden automatizar en CI porque exigen un
equipo real (Windows o Ubuntu de escritorio), las apps de Codex o Claude
Desktop instaladas, cuentas autorizadas y, en algunos casos, el cliente
OAuth real. Ninguna requiere datos ni carpetas de Drive de producción; usar
siempre cuentas y carpetas de prueba autorizadas explícitamente. No guardar
tokens, rutas privadas completas ni contenido de licitaciones en capturas o
incidencias.

Comprobaciones de compatibilidad Windows de Core/harness (no de
instalación): `windows_manual.md`.

## Antes de empezar

- Registrar: sistema operativo y versión, versión de la app (Codex App o
  Claude Desktop), versión de Git, versión de uv, versión de `litman`
  instalada.
- Usar una cuenta de prueba de Google Workspace que no sea la cuenta
  principal del administrador, para no confundir el resultado con permisos
  especiales de admin.

## 1. Primer paso: el límite de tiempo de las herramientas MCP

Es la comprobación más importante: si falla, el diseño síncrono no es
viable y hay que retomar el análisis asíncrono antes de seguir con el resto.

1. Registrar el MCP `litman` con un `tool_timeout_sec`/`timeout` alto (2h).
2. Lanzar una herramienta que tarde varios minutos (puede simularse con un
   `sleep` en un servidor MCP de prueba, sin tocar `litman-mcp`) desde:
   - la app de Codex (Windows);
   - Claude Desktop, pestaña Code (Windows y Ubuntu).
3. Confirmar que la llamada no se corta a los ~60s por defecto y que el
   resultado llega completo. Si se corta en alguna app, anotar la versión
   exacta y el comportamiento (error devuelto, silencio, reintento).

## 2. Instalación de extremo a extremo

Repetir en Windows 10/11 y en Ubuntu, con la app de Codex y con Claude
Desktop, con `git` y `uv` ya instalados:

4. Pegar la frase de instalación documentada en el README. Confirmar que
   `install.ps1`/`install.sh` termina sin error y pide reiniciar la app.
5. Reiniciar la app, abrir la carpeta del entorno LitMan y escribir
   "prepara mi equipo". Confirmar que la skill `preparar-equipo` aparece y
   conduce los pasos en orden.
6. Confirmar que el subagente `lector-licitacion` se puede invocar desde la
   app (hay un reporte de comunidad de "unknown agent_type" al invocar
   subagentes personalizados desde la app de escritorio de Codex;
   confirmar si reproduce aquí).
7. Confirmar que el modelo configurado en el subagente está disponible en
   el plan personal usado para la prueba (Codex: `gpt-5.6-luna`; Claude: el
   modelo configurado del subagente lector).

## 3. Prerrequisitos ausentes: el instalador no debe instalarlos solo

8. Sin Git instalado: confirmar que el script se detiene y muestra el
   enlace oficial exacto, sin intentar instalarlo.
9. Sin uv instalado: confirmar que el script se detiene y muestra el
   comando oficial de un solo paso, sin ejecutarlo por su cuenta.
10. Sin la CLI del proveedor (`codex`/`claude`) en el PATH aunque la app
    esté instalada: confirmar que el script se detiene con el enlace de
    instalación oficial de esa CLI, sin ejecutarlo.
11. Sin navegador (Chrome/Edge) para el PDF: confirmar que `preparar-equipo`
    lo señala como aviso (no bloquea el resto) y explica que su instalación
    en Ubuntu requiere `sudo`, por lo que la hace la persona o su IT.

## 4. CLI y sesión del proveedor

12. **Codex.** Comprobar si la app de escritorio deja `codex` en el PATH y
    si comparte `~/.codex/auth.json` con la CLI, o si hace falta un login
    aparte. Confirmar en Windows y Ubuntu.
13. **Claude.** Comprobar si Claude Desktop deja `claude` en el PATH y
    comparte sesión con la CLI. Confirmar si el instalador nativo
    (`install.ps1` de Anthropic) pide permisos de administrador en
    Windows.

## 5. Cliente OAuth y segunda cuenta

14. Entregar `client_secret.json` por el canal seguro habitual a una
    segunda persona con una segunda cuenta de Workspace (no la cuenta ya
    usada en el smoke del 2026-10-15). Ejecutar `litman install
    --oauth-client` con la ruta del archivo que esa persona descargó, y
    confirmar que se copia con permisos privados y que el original se
    borra solo si se confirma.
15. Ejecutar `litman login` con esa segunda cuenta y confirmar con
    `diagnose`, `inspect` y `status` que recupera un expediente de prueba
    por ID.
16. Confirmar que, al ser el cliente de audiencia Interna, no aparece el
    aviso de "app no verificada" ni caduca el token a los 7 días (repetir
    `diagnose` pasados varios días).

## 6. Actualizar, reparar y desinstalar

17. Con LitMan ya instalado, publicar una nueva etiqueta `v*` del repo y
    repetir la frase de instalación. Confirmar que actualiza sin duplicar
    el bloque MCP ni las skills.
18. Simular un fallo (p. ej. borrar el token) y confirmar que
    `preparar-equipo` lo detecta con `diagnose` y lo repara guiando de
    nuevo el paso que falta.
19. Ejecutar `uninstall.ps1`/`.sh`. Confirmar que solo borra lo que registra
    el manifiesto de instalación, que las CLI de Codex/Claude, Git y uv
    quedan intactos, y que la carpeta del entorno LitMan solo se borra si
    la persona lo confirma.

## Cierre de la comprobación futura

Anotar por cada sistema, app y proveedor: versión, caso ejecutado,
resultado, evidencia local no sensible y fallo reproducible. Si algo falla,
abrir una corrección acotada contra `distribucion-instalacion`, repetir la
comprobación y actualizar esta lista.
