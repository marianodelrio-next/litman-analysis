# Guía de LitMan: instalación y uso

## Antes de empezar

LitMan analiza los expedientes de licitación que tienes en Google Drive y te prepara un resumen. Lo usas escribiendo en la aplicación Codex, como si hablaras con un asistente. La instalación se hace una sola vez y lleva unos 30–45 minutos.

Comprueba que tienes todo esto antes de empezar:

- [ ] Un ordenador con Windows 10 u 11 y conexión a internet.
- [ ] Una cuenta de ChatGPT/OpenAI para entrar en la aplicación Codex.
- [ ] Tu cuenta de Google de trabajo (la que tiene acceso a las carpetas de licitaciones en Drive).
- [ ] El archivo `client_secret.json` que te ha enviado el equipo técnico por un canal seguro. No lo reenvíes ni lo subas a ningún sitio.
- [ ] Microsoft Edge (viene con Windows) o Google Chrome.

LitMan en sí no necesita permisos de administrador. Git y Node.js pueden pedirlos al instalarse: si tu usuario no los tiene, pide a IT que instale esos dos programas.

## Paso 1: instalar los programas necesarios

LitMan necesita cuatro programas: la aplicación Codex, Git, uv y la herramienta de comandos de Codex. Se instalan una vez y luego no tienes que tocarlos.

**Cómo abrir PowerShell** (lo usarás varias veces): pulsa la tecla Windows, escribe `PowerShell` y haz clic en **Windows PowerShell**. No elijas "Ejecutar como administrador". Para pegar un comando, cópialo de esta guía, haz clic derecho dentro de la ventana y pulsa Intro.

**Importante:** después de instalar cada programa, cierra PowerShell y ábrela de nuevo. Si no, Windows no lo encuentra.

1. **Aplicación Codex.** Descárgala desde la página oficial de OpenAI (si dudas, pide el enlace al equipo técnico), instálala y entra con tu cuenta.
2. **Git.** En PowerShell pega:

   ```powershell
   winget install --id Git.Git -e
   ```

   Acepta las condiciones si te las pide (escribe `Y` y pulsa Intro). También puedes descargarlo desde [git-scm.com/downloads/win](https://git-scm.com/downloads/win) y pulsar Siguiente en todo.
3. **uv.** En una PowerShell nueva pega:

   ```powershell
   irm https://astral.sh/uv/install.ps1 | iex
   ```
4. **Herramienta de comandos de Codex.** En una PowerShell nueva escribe `codex --version`.
   - Si aparece un número de versión, ya la tienes: pasa al paso 2.
   - Si dice que no reconoce `codex`, instálala así (dos comandos, cerrando y abriendo PowerShell entre ellos):

   ```powershell
   winget install --id OpenJS.NodeJS.LTS -e
   ```

   ```powershell
   npm install -g @openai/codex
   ```

   Vuelve a escribir `codex --version` para comprobarlo.

Si te saltas alguno, no pasa nada: el instalador de LitMan (paso 2) se detiene y te dice cuál falta.

## Paso 2: instalar LitMan

LitMan se instala pegando un solo comando. Tarda unos minutos.

1. Abre una PowerShell nueva (no como administrador).
2. Copia esta línea entera, pégala y pulsa Intro:

   ```powershell
   $env:LITMAN_APP='codex'; irm https://raw.githubusercontent.com/marianodelrio-next/litman-analysis/master/harness/deployment/install.ps1 | iex
   ```
3. Espera a que termine. Si todo va bien, verás:

   ```text
   Instalacion completa. Para terminar:
     1. Cierre y vuelva a abrir la aplicacion.
     2. Abra la carpeta LitMan (%USERPROFILE%\LitMan).
     3. Escriba: prepara mi equipo
   ```
   Funciona aunque tu nombre de usuario de Windows lleve tildes (por ejemplo, `María Núñez`) y con el Control inteligente de aplicaciones activado: no hace falta desactivarlo.
4. Si en cambio sale un mensaje que empieza por **Falta**, el instalador te dice qué programa falta:

| Mensaje | Qué hacer |
| --- | --- |
| `Falta Git` | Instala Git (paso 1, punto 2). |
| `Falta uv` | Instala uv (paso 1, punto 3). |
| `Falta la CLI de Codex` | Instala la herramienta de comandos de Codex (paso 1, punto 4). |

Después, abre una PowerShell nueva y vuelve a pegar el comando. Puedes repetirlo las veces que haga falta sin romper nada.

LitMan crea una carpeta llamada **LitMan** dentro de tu carpeta de usuario (por ejemplo `C:\Users\tu-nombre\LitMan`). Es la carpeta que abrirás en Codex. Dentro no se guardan licitaciones: todo sigue en Google Drive.

## Paso 3: configurar el equipo

La configuración la guía el propio asistente: solo tienes que escribir **prepara mi equipo** y seguir lo que te pida.

1. **Cierra la aplicación Codex del todo y vuelve a abrirla.**
2. En Codex, abre la carpeta **LitMan** de tu carpeta de usuario.
3. Escribe: **prepara mi equipo**
4. El asistente revisa el equipo y te dice en una frase qué falta. Luego te pide, por este orden:
   1. **El archivo `client_secret.json`.** Te pedirá dónde está. Para copiar la ruta: en el Explorador de archivos, mantén pulsada la tecla Mayúsculas, haz clic derecho sobre el archivo y elige **Copiar como ruta**. Pégala en el chat. Si te pregunta si quieres borrar el original, puedes decir que sí: LitMan ya guarda su propia copia.
   2. **Entrar en Google.** Se abre el navegador. Elige tu cuenta de Google de trabajo y acepta los permisos sobre Drive. Cuando el navegador diga que ya puedes cerrarlo, vuelve a Codex.
   3. **Sesión de Codex.** Si hace falta, el asistente te dará un comando (normalmente `codex login`) para que lo pegues tú en PowerShell. Se abre el navegador para entrar con tu cuenta de OpenAI.
5. Al final el asistente repite la revisión y te confirma que todo está listo.

Si Codex te pide permiso para ejecutar un comando `litman`, acéptalo: es LitMan haciendo la configuración.

Si te avisa de que **no encuentra el navegador para PDF**, no es grave: podrás analizar igual, pero no se generará el resumen en PDF. Avisa al equipo técnico.

## Paso 4: primera prueba

La primera prueba se hace con una **copia de una licitación de ejemplo** en Drive, no con una real en curso. Así, si algo sale mal, no afecta a nada.

**Preparar la carpeta de prueba.** Crea en Drive una carpeta con los documentos de una licitación antigua o de ejemplo (pliegos, anuncio, etc.).

**Obtener el ID de la carpeta.** Abre la carpeta en Drive y mira la dirección del navegador. El ID es lo que va después de `folders/`:

```text
https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz
                                       └──────── este es el ID ────────┘
```

**Conectar y analizar.**

1. En Codex, con la carpeta LitMan abierta, escribe: **conecta la licitación con ID** y pega el ID.
2. El asistente te cuenta qué hay en la carpeta y te propone el siguiente paso. Antes de cambiar nada en Drive te enseña un **plan** y espera tu sí.
3. Ve aceptando los pasos que te proponga. El recorrido habitual es:
   1. **Preparar la carpeta**: organiza la carpeta, coloca los pliegos en la carpeta `Originales` y crea una carpeta interna `_LitMan` que no debes tocar. Si tu permiso en Drive permite mover archivos, los pliegos se mueven; si solo permite copiarlos, se copian en `Originales` y el archivo de la raíz se queda donde estaba (LitMan nunca borra nada); si no permite ninguna de las dos cosas, se quedan donde están y el asistente te avisa.
   2. **Analizar**: LitMan lee los documentos y prepara el análisis inicial. Puede tardar de varios minutos a media hora; no cierres Codex mientras tanto.
   3. **Publicar**: sube el resultado (ficha de la oportunidad y resumen) directamente a la carpeta `Analisis inicial` (o `Analisis detallado`), sin subcarpetas. Si repites un análisis, los archivos nuevos llevan la fecha en el nombre, por ejemplo `ficha_oportunidad (2026-10-19).pdf`; LitMan no sobrescribe ni borra los anteriores.
   4. **Resumen de contexto**: te propone una ficha con objeto, organismo, presupuesto, fecha límite, etc. Cada dato indica de qué documento sale; si un dato no aparece, pone "No consta".
   5. **Análisis detallado**: te pregunta si lo quieres. Es una decisión de negocio: contesta sí o no.
4. Abre la carpeta en Drive y revisa lo que se ha publicado.

**La prueba ha ido bien si:** el análisis aparece publicado en Drive, los nombres con tildes y ñ se ven bien, el PDF se abre y los datos del resumen coinciden con los pliegos.

## Uso diario

En el día a día solo necesitas abrir Codex en la carpeta LitMan y escribir lo que quieres hacer.

| Quiero… | Escribe en Codex |
| --- | --- |
| Analizar una licitación nueva | `conecta la licitación con ID <ID de la carpeta>` |
| Seguir con una licitación ya conectada | `¿cómo va la licitación con ID <ID>?` |
| Actualizar el resumen tras añadir documentos | `actualiza el resumen de la licitación con ID <ID>` |
| Descartar un análisis que no quiero publicar | `descarta el análisis` |
| Leer o cambiar el texto de un Google Doc de la licitación (por ejemplo, la propuesta técnica en `Oferta`) | `en la propuesta técnica, cambia "<texto actual>" por "<texto nuevo>"` |
| Crear un Google Doc nuevo en la licitación | `crea en la carpeta Oferta un documento "<nombre>" con este texto: ...` o `crea un Google Doc a partir del DOCX "<nombre>"` |
| Ver qué hay en una carpeta de la licitación o buscar un archivo | `qué hay en la carpeta Oferta` o `busca el archivo del presupuesto` |
| Leer un archivo de la licitación (PDF, Word, Excel, Hojas de cálculo, Presentaciones, texto) | `lee el Excel de costes` |
| Ver los comentarios de un archivo | `qué comentarios hay en la memoria técnica` |
| Organizar carpetas o archivos | `crea una carpeta Entregas y mueve ahí la oferta final` |
| Saber qué puede hacer LitMan, con ejemplos | `qué puedes hacer` |
| Arreglar algo que no funciona | `prepara mi equipo` |

Cuatro reglas:

- **Nada se cambia en Drive sin tu sí.** El asistente siempre te enseña el plan antes. Léelo y contesta sí o no.
- **No toques la carpeta `_LitMan`** ni el archivo `contexto.md` a mano. Si alguien los edita, LitMan no los sobrescribe y te avisará.
- **Para organizar archivos, también hay plan.** Antes de crear carpetas, renombrar, mover, copiar, enviar a la papelera, exportar o convertir, LitMan te muestra el origen, el destino y el nombre final. Los originales y los archivos internos están protegidos; si faltan permisos, el asistente te lo explica. La papelera nunca borra un archivo de forma permanente.
- **Las licitaciones y los archivos de Drive se tocan solo con LitMan, nunca con el navegador ni manejando la pantalla.** Si pides algo que LitMan todavía no sabe hacer, el asistente te lo dirá y te sugerirá pedírselo al desarrollador de LitMan. Para editar o crear un Google Doc, el asistente te enseña cada cambio con el texto de alrededor y solo lo aplica si dices que sí. Puede cambiar el texto y dar formato básico (estilo de párrafo como título o encabezado, negrita, cursiva, subrayado, viñetas y listas numeradas), pero no mezcla texto y formato en una misma vista previa; también puede crear un documento nuevo a partir de un texto en Markdown. Las tablas, las imágenes y los comentarios los cambias tú en Google Docs. Un DOCX no se edita directamente: primero se crea su Google Doc.
- **Antes de descartar un análisis, cierra** los archivos suyos que tengas abiertos (por ejemplo un PDF). Si no, el descarte falla y tendrás que repetirlo.

## Problemas frecuentes

Para casi cualquier problema, lo primero es escribir **prepara mi equipo**: el asistente revisa todo y arregla solo lo que falla.

| Qué ves | Qué hacer |
| --- | --- |
| PowerShell dice que no reconoce `git`, `uv` o `codex` justo después de instalarlos | Cierra PowerShell y ábrela de nuevo. |
| Codex no reconoce "prepara mi equipo" | Cierra Codex del todo, ábrelo y comprueba que tienes abierta la carpeta **LitMan**. |
| El navegador no vuelve a Codex después de entrar en Google | Puede ser el antivirus o el cortafuegos. Escribe "prepara mi equipo" para reintentarlo; si sigue igual, avisa a IT. |
| Windows avisa de que el Control inteligente de aplicaciones ha bloqueado `litman.exe`, o sale `No se encuentra el interprete de LitMan` | Vuelve a pegar el comando de instalación del paso 2 y, al terminar, escribe "prepara mi equipo". La versión actual de LitMan ya no usa `litman.exe`. No desactives el Control inteligente de aplicaciones; si sigue pasando, avisa al equipo técnico. |
| Google dice "aplicación no verificada" | Para y avisa al equipo técnico: no debería pasar. |
| Un mensaje dice que la ruta de trabajo es demasiado larga | Los documentos con nombres largos ya se acortan solos en tu equipo (en Drive no cambian), así que solo pasa si se ha configurado una carpeta de trabajo muy profunda. Avisa al equipo técnico: hay que configurar una carpeta de trabajo con un nombre más corto. |
| El descarte de un análisis falla con "Fallo inesperado del harness" | Cierra los archivos de ese análisis que tengas abiertos y vuelve a descartarlo. |
| Te avisa de que la API de Google Sheets no está habilitada | Avisa al equipo técnico: hay que habilitarla una vez en el proyecto de Google Cloud. Mientras tanto, el resto de LitMan funciona. |
| Te dice que un archivo es demasiado grande para leerlo | LitMan lee archivos de hasta 30 MB y hojas de hasta 200.000 celdas. Pide solo la parte que necesitas o abre el archivo tú mismo. |
| Te avisa de que la API de Google Docs no está habilitada | Avisa al equipo técnico: hay que habilitarla una vez en el proyecto de Google Cloud. Mientras tanto, el resto de LitMan funciona. |
| Al aplicar un cambio en un documento, te avisa de que el documento cambió | No se ha escrito nada: alguien lo editó después de la vista previa. Pide al asistente que lo vuelva a leer y te prepare el cambio de nuevo. |
| Te avisa de que alguien ha cambiado `contexto.md` | No es un error. El asistente te lo explica y no sobrescribe nada; solo se sustituye si tú se lo pides. |

Si avisas al equipo técnico, copia el mensaje de error tal cual. No envíes capturas con documentos de licitaciones ni el archivo `client_secret.json`.

## Actualizar y desinstalar

**Actualizar.** Pega en PowerShell el mismo comando del paso 2 y, al terminar, cierra y vuelve a abrir Codex. Tu configuración y tu sesión de Google se conservan.

**Desinstalar.** Cierra Codex y cualquier archivo de la carpeta LitMan. Luego, en PowerShell, pega:

```powershell
cd $HOME; powershell -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\LitMan\src\harness\deployment\uninstall.ps1"
```

Al terminar verás `LitMan desinstalado.` Por defecto se conservan la carpeta LitMan, tu sesión de Google y el archivo de cliente, por si vuelves a instalarlo. Codex, Git y uv no se tocan.

Para borrar también la carpeta LitMan, pon delante `$env:LITMAN_REMOVE_WORKSPACE='1';`. Para borrar también la sesión de Google y los datos locales, pon delante `$env:LITMAN_PURGE_DATA='1';`.

Si sale "No se pudieron eliminar algunos elementos", cierra el programa que esté usando esos archivos y repite el comando.

## Anexo: hoja de comprobación para la prueba

Esta lista es para quien valida la guía en un Windows limpio. Apunta el resultado de cada punto, sin tokens, rutas privadas completas ni contenido de licitaciones.

**Instalación**

- [ ] Apuntadas las versiones de Windows, la aplicación Codex, `codex --version`, `git --version` y `uv --version`.
- [ ] Al ejecutar el paso 2 sin Git, sale `Falta Git` y no se instala nada.
- [ ] Sin uv, sale `Falta uv` con el comando para instalarlo.
- [ ] Sin la herramienta de comandos de Codex, sale `Falta la CLI de Codex` y no se descarga el repositorio.
- [ ] Apuntado si la aplicación Codex instala por sí sola el comando `codex` o si hubo que instalarlo aparte.
- [ ] Apuntado si, cuando el instalador falla, la ventana de PowerShell sigue abierta y el error se lee.
- [ ] El instalador termina con "Instalacion completa".

**Configuración**

- [ ] "prepara mi equipo" arranca y sigue los pasos en orden.
- [ ] El inicio de sesión en Google funciona sin aviso de "aplicación no verificada".
- [ ] Apuntado si la sesión de Codex está en `%USERPROFILE%\.codex\auth.json` o en el Administrador de credenciales, y si la comparten la aplicación y la herramienta de comandos.
- [ ] Unos días después, "prepara mi equipo" sigue en verde sin volver a entrar en Google.

**Uso**

- [ ] Conectar, analizar, publicar y resumir funciona con la licitación de ejemplo.
- [ ] Un análisis de varios minutos no se corta.
- [ ] Los nombres con tildes, ñ y símbolos como € se ven bien en Drive y en el PDF.
- [ ] Dos documentos con el mismo nombre visible se tratan como distintos.
- [ ] Apuntado qué navegador se usa para el PDF (Edge o Chrome).
- [ ] Pedir un cambio de texto en la propuesta técnica muestra la vista previa y, tras aceptarla, el cambio aparece en Google Docs; el asistente no abre el navegador.
- [ ] Crear un Google Doc nuevo en la licitación funciona desde un texto y desde un DOCX.
- [ ] Preguntar qué hay en una carpeta, buscar un archivo por su nombre y leer un PDF, un Excel, una hoja de cálculo de Google y una presentación funciona sin que el asistente use el navegador.
- [ ] Pedir los comentarios de un documento muestra solo los abiertos, con sus respuestas.
- [ ] "qué puedes hacer" muestra lo que hace LitMan, agrupado y con un ejemplo para cada cosa.
- [ ] Pedir algo que LitMan no sabe hacer: el asistente dice que no tiene herramienta para eso, sugiere pedírselo al desarrollador y no usa el navegador ni maneja la pantalla.
- [ ] Descartar con un archivo abierto falla con "Fallo inesperado del harness". Tras cerrarlo, el descarte funciona.
- [ ] Tras borrar `token.json` en `%LOCALAPPDATA%\litman-harness`, "prepara mi equipo" solo repite el inicio de sesión en Google.

**Desinstalación**

- [ ] Con un archivo de la carpeta LitMan abierto y `LITMAN_REMOVE_WORKSPACE=1`, sale "No se pudieron eliminar algunos elementos" y LitMan sigue instalado.
- [ ] Tras cerrar el archivo y repetir, sale `LitMan desinstalado.` y la carpeta LitMan ha desaparecido.

**Pruebas automáticas** (solo perfil técnico, antes de desinstalar): clona el repositorio en una ruta corta como `C:\lt` y ejecuta `uv run pytest -q` dentro de `core` y de `harness`.
