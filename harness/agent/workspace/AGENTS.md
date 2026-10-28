# LitMan

Esta carpeta es el espacio de trabajo de LitMan. Aquí no se guardan
licitaciones ni documentos: todo vive en Google Drive y LitMan sólo lo
analiza por tu cuenta cuando se lo pides.

- Para empezar o si algo no funciona, escribe: **"prepara mi equipo"**.
- Para analizar una licitación, escribe: **"conecta la licitación con ID
  ..."** (usa la skill `conectar-licitacion`).
- Para saber qué puede hacer LitMan, escribe: **"qué puedes hacer"** (usa la
  skill `ayuda-litman`).
- Para actualizar LitMan, escribe: **"actualiza mi equipo"** (usa la skill
  `actualizar-equipo`).
- Para cambiar el proveedor o modelo de los análisis, usa `setup`. Si sólo
  se pide cambiar el modelo, consulta `diagnose` para conservar el proveedor
  configurado; si no hay proveedor configurado, pregunta cuál usar. Un modelo
  `null` significa que Core usa el modelo predeterminado del proveedor. Al
  omitir el modelo en `setup` se vuelve a ese valor predeterminado. Los planes
  de análisis ya preparados conservan su proveedor y modelo anteriores.
- Para ver qué hay en una licitación usa `list_folder`, `search_in_dossier` y
  `get_file_info`; para leer un archivo (PDF, DOCX, texto, Excel, Google Docs,
  Sheets o Slides) usa `read_file`, y para ver sus comentarios `list_comments`.
- Los comentarios nuevos se anclan a una frase exacta o al título de una
  sección de un Google Doc con `preview_comment_changes`/`apply_comment_changes`
  (nunca comentarios generales); ante `comment_write_uncertain`, no se reenvía:
  la persona lo revisa en Google Docs.
- Los Google Docs de una licitación se leen con `read_google_doc`, se editan
  (texto o formato, incluidos resaltado y enlaces `http(s)` que se ponen,
  cambian o quitan) con `preview_document_edit`/`apply_document_edit` y se
  crean con `preview_document_creation`/`apply_document_creation`, aplicando
  sólo la vista previa que la persona acepte.
- Las hojas de cálculo de Google Sheets se cambian con
  `preview_sheet_edit`/`apply_sheet_edit` (actualizar un rango o añadir
  filas), aplicando sólo la vista previa que la persona acepte.
- Para licitaciones y archivos de Drive usa sólo las herramientas de LitMan.
  Nunca uses computer use, el navegador, otros conectores de Drive, scripts
  ni las APIs de Google directamente. Si ninguna herramienta de LitMan lo
  permite, dilo y sugiere pedírselo al desarrollador de LitMan.

El comando `litman` de este equipo es: `{{LITMAN_BIN}}`
