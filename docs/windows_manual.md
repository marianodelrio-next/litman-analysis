# Comprobaciones manuales de Windows nativo

Las tareas de compatibilidad de Core y harness ya están implementadas y
probadas en Ubuntu. Esta lista se usará **cuando haya un equipo Windows 10/11
disponible**; la validación nativa sigue pendiente. No usar cuentas,
credenciales, carpetas de Drive ni recursos de producción: las pruebas que los
necesiten requieren autorización explícita
y datos de prueba. No guardar tokens, rutas privadas completas ni contenido de
licitaciones en capturas o incidencias.

## Preparar el entorno de prueba

- Registrar edición y versión de Windows, versión de Python 3.11, versiones de
  Core y harness instaladas, `codex --version`, `claude --version` y las rutas
  resueltas de `codex`, `claude` y `litman-core`. Usar PowerShell nativo, sin
  WSL. La instalación detallada de uv, plugin y prerrequisitos pertenece a la
  tarea de instalación.
- Repetir las pruebas principales en Windows 10 y 11 cuando ambos estén
  disponibles. Un runner de GitHub Actions no sustituye estas comprobaciones
  de escritorio; CI Windows se añadirá en otra fase.
- Usar una carpeta corta del perfil, un expediente sintético con texto español
  y un directorio de salida desechable. Registrar solo versión, resultado,
  error y ruta *relativa* del artefacto que falle.
- Ejecutar las suites de Core y harness en PowerShell nativo (`uv run pytest
  -q` desde cada paquete), además de las comprobaciones de extremo a extremo
  siguientes. Registrar las pruebas omitidas y su motivo.

## Core y límite Core–harness

1. **Ejecutable instalado y contrato.** Ejecutar `litman-core info`,
   `litman diagnose` y `litman setup` con el proveedor de prueba. Confirmar
   que el harness encuentra `litman-core.exe` del mismo entorno Python y que
   `info` devuelve `contract: 1`. Si falla, anotar la ruta real del lanzador
   sin publicar datos de usuario. Verificar que el estado del harness queda
   bajo `%LOCALAPPDATA%\litman-harness` y que `LITMAN_HARNESS_*`, XDG y
   `CODEX_HOME` explícitos siguen apuntando a sus rutas configuradas.
2. **Unicode por pipes.** Ejecutar un trabajo sintético cuyo nombre y texto
   contengan `ñ`, tildes y un carácter fuera de cp1252. Leer el JSON de Core
   mediante el harness y comprobar que nombres, errores y artefactos no tienen
   caracteres sustituidos. La prueba apunta al caso en que Python escribe en
   stdout redirigido usando una página de códigos local.
3. **Rutas y nombres.** Preparar originales de prueba con `PCAP`, `anuncio` y
   `adjudicación` en el nombre. Para caracteres que Windows no admite, nombres
   reservados, punto final y longitud elevada, usar recursos simulados de
   Drive o una carpeta Drive de prueba autorizada: esos nombres no pueden
   crearse directamente como archivos locales Windows. Confirmar que cada copia local
   existe, que `input_snapshot` relaciona `file_id`, nombre original y
   `local_name`, que MD5/SHA-256 coinciden y que la clasificación de Core para
   los nombres reconocibles se conserva. Comprobar dos originales con igual
   nombre visible y distinto ID; no debe sobrescribirse ninguno.
4. **Ruta profunda.** Repetir con un directorio de trabajo configurado muy
   profundo. Si el límite se alcanza, debe aparecer un error temprano que
   indique elegir un `LITMAN_HARNESS_WORK_DIR` más corto; no se debe dejar una
   descarga parcial como operación publicada. No activar `LongPathsEnabled`
   para hacer pasar esta prueba.
5. **Publicación y descarte.** Completar un análisis local sintético, publicar
   los artefactos de prueba o descartarlo según corresponda y comprobar que
   se eliminan los workspaces temporales con archivos de solo lectura. Abrir
   deliberadamente un archivo de un workspace de prueba con otro proceso y
   repetir el descarte: debe informar el bloqueo y conservar un estado
   recuperable, nunca declarar que borró una carpeta que aún existe.

## CLI autenticadas: comprobaciones aplazadas

Estas pruebas se harán después de contar con cuentas de prueba autorizadas.
Su resultado determinará si el flujo nativo está listo para uso real.

6. **Claude Code nativo.** Localizar el `claude.exe` efectivo y registrar su
   versión; comprobar si existe también un `.cmd` y cuál resolvería el
   proveedor. Con una sesión de prueba, ejecutar `assessment` y
   `detailed-analysis` con el esquema real, confirmar `structured_output` y
   revisar que `--restricted`, `--permission-mode dontAsk`,
   `--permission-prompts none` y `--tools Read` permiten leer el expediente
   sintético sin conceder escritura. Un resultado con el esquema corto no
   demuestra que el esquema detallado funcione.
7. **Codex nativo.** Comprobar si la sesión de prueba está en
   `%USERPROFILE%\.codex\auth.json` o en el almacén de credenciales del
   sistema. Ejecutar el comando de Core sobre datos sintéticos con el modo
   de autenticación admitido. Revisar los eventos y cualquier herramienta
   ejecutada. La opción actual `--dangerously-bypass-approvals-and-sandbox`
   requiere una decisión explícita sobre el aislamiento aceptable fuera de
   Docker antes de considerar el flujo nativo listo para uso real.

## PDF, OAuth y privacidad local: comprobaciones aplazadas

8. **Navegador PDF.** Con Chrome y/o Edge instalados, generar la ficha desde
   un resultado sintético. Confirmar cuál ejecutable se eligió, que el PDF se
   abre, contiene los caracteres españoles y respeta el máximo de páginas.
   Repetir con una ruta que tenga espacios y provocar un fallo controlado del
   navegador para comprobar que el diagnóstico se puede leer, incluso si
   emite caracteres fuera de la página de códigos local. Encontrar
   `msedge.exe` no prueba por sí solo que su impresión headless funcione en esa
   versión.
9. **OAuth de escritorio.** Solo con un cliente OAuth y una carpeta Drive de
   prueba autorizados, ejecutar `litman login`, completar el navegador y
   confirmar el callback local y un refresco posterior. Si falla el callback,
   comprobar si firewall o política del equipo bloquean loopback. No copiar
   el token a tickets ni logs.
10. **ACL del perfil.** Revisar los permisos efectivos del directorio de
    estado, `settings.toml`, `token.json` y `CODEX_HOME/auth.json` de prueba.
    Verificar que se heredan del perfil previsto. Los modos `0600`/`0700` de
    Python no prueban privacidad en Windows; registrar solo si la ACL es
    adecuada, sin copiar su contenido sensible.

## Cierre de la comprobación futura

Anotar por cada sistema y proveedor: versión, caso ejecutado, resultado,
evidencia local no sensible y fallo reproducible. Si una comprobación falla,
abrir una corrección acotada, volver a ejecutar la suite pertinente en Ubuntu
y en Windows, y actualizar esta lista. La matriz CI `ubuntu-latest` y
`windows-latest` para Core y harness queda como trabajo posterior; no es parte
de las dos tareas de implementación inicial.
