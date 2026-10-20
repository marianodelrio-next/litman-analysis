---
name: preparar-equipo
description: Prepara, repara, actualiza o desinstala LitMan en este equipo guiando a la persona paso a paso, sin ejecutar nunca un instalador de Git, uv, la CLI del proveedor o un navegador por su cuenta.
---

Úsala cuando la persona escriba "prepara mi equipo", algo no funcione o
quiera actualizar/desinstalar. Nunca instales Git, uv, la CLI del proveedor
ni un navegador: eso lo decide y ejecuta la persona, tú sólo detectas y
explicas.

1. Llama a `diagnose` y resume en una frase de negocio qué falta (no
   muestres rutas locales).
2. **Cliente OAuth de Drive.** Si falta, pide la ruta del archivo que
   Mariano le entregó por canal seguro (nunca un enlace del repo) y ejecuta
   `litman install --oauth-client <ruta>`. Sólo añade `--delete-original`
   si la persona confirma explícitamente que quiere borrar el archivo
   original tras copiarlo.
3. **Drive.** Ejecuta `litman login` (abre el navegador; la persona elige
   su cuenta de Workspace).
4. **Sesión del proveedor.** Si `diagnose`/`info.environment` indica que la
   CLI del proveedor (Codex o Claude Code) no tiene sesión, dale el comando
   de login de esa CLI para que lo ejecute ella misma; no lo ejecutes tú
   salvo que lo pida explícitamente en ese turno.
5. **Google Docs y Google Sheets.** Si `diagnose` devuelve `docs_api` igual a
   `disabled`, explica que el administrador del proyecto de Google Cloud del
   cliente OAuth debe habilitar una vez la Google Docs API; si devuelve
   `sheets_api` igual a `disabled`, debe habilitar la Google Sheets API. Hasta
   entonces no se pueden leer ni editar esos archivos, pero el resto de
   LitMan funciona. Con `unknown` (sin sesión de Drive o sin conexión), repite
   la comprobación tras `litman login`; no bloquees por ello.
6. Ejecuta `setup` con el proveedor por defecto de esta app (Codex →
   `codex`, Claude → `claude-code`) y el modelo si la persona lo pide.
7. Vuelve a llamar a `diagnose`. Si todo está en verde salvo pasos humanos
   ya hechos, pasa a la skill `conectar-licitacion`. Si el navegador PDF no
   está disponible, avísalo sin bloquear: en Ubuntu su instalación requiere
   `sudo`, así que la hace la persona o su IT, nunca tú.

**Actualizar.** Pide que vuelva a pegar la frase de instalación de la app
(README) y que reinicie la aplicación.

**Reparar.** Repite `diagnose` y resuelve sólo el paso que falle.

**Desinstalar.** Explica que existe `uninstall.sh`/`uninstall.ps1` (ver
README) y qué conserva por defecto (token, cliente OAuth y la carpeta
LitMan sólo se borran si la persona lo pide explícitamente).
