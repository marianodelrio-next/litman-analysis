# Desarrollo del harness de expediente

`harness/` es una distribución Python separada de `litman_core` (`litman-harness`).
Conecta **una** licitación por el ID de su carpeta de Drive, con la cuenta OAuth
personal de cada empleado, y expone las mismas operaciones por CLI (`litman`) y
MCP stdio (`litman-mcp`). Nunca usa la cuenta de servicio ni el publicador Drive
de Core, y no acepta tokens ni secretos por argumentos, stdio, manifiesto o
contexto.

## Estructura

```text
harness/src/litman_harness/
  errors.py            HarnessError y mensaje seguro para errores inesperados
  local_paths.py       rutas privadas (estado, configuración) y rechazo del clon
  plans/               Plan, PlanAction, OperationRecord y PlanStore local privado
  dossier/             Resource, pertenencia, manifiesto v1, contexto.md,
                       capacidad de estado compartido, ExpedienteService
                       (inspect/status/incorporación), PublicationService y
                       SummaryService (read_document y resumen)
  analysis/            originales y descarga, validación del run y catálogo
                       público, AnalysisService (Core local)
  adapters/            Drive (OAuth personal), estado compartido Drive v2
                       (`drive_state.py`), extracción de texto PDF/DOCX
                       (`documents.py`), metadatos de desarrollo, OAuth de
                       escritorio y proceso `litman-core`
  interfaces/          assembly (configuración), registro de operaciones
                       (tools/), CLI y MCP
harness/agent/skills/{conectar-licitacion,resumir-licitacion}/SKILL.md   skills de producto
harness/agent/claude/agents/lector-licitacion.md    subagente lector (Claude Code)
harness/agent/codex/agents/lector-licitacion.toml   subagente lector (Codex)
harness/tests/{dossier,analysis,adapters,interfaces,plans}/
```

`dossier/membership.py` contiene la única comprobación de pertenencia: sigue la
cadena de IDs de padres hasta la carpeta conectada dentro de la misma unidad,
sin búsquedas globales.

## Arranque de desarrollo

```bash
cd harness
UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv sync
UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q
```

Configuración local (variables de entorno; ninguna
ruta puede estar dentro del clon, que se detecta subiendo desde el paquete hasta
`.git`):

| Variable | Uso | Defecto |
| --- | --- | --- |
| `LITMAN_HARNESS_METADATA` | JSON de metadatos no secretos, sólo lectura, para desarrollo | sin definir → OAuth |
| `LITMAN_HARNESS_OAUTH_CLIENT` | cliente OAuth de escritorio (sólo para `login`) | `$XDG_CONFIG_HOME/litman-harness/client_secret.json` |
| `LITMAN_HARNESS_OAUTH_TOKEN` | token personal (0600) | `$XDG_CONFIG_HOME/litman-harness/token.json` |
| `LITMAN_HARNESS_PLAN_STORE` | planes y operaciones locales (0700/0600) | `$XDG_STATE_HOME/litman-harness/plans` |
| `LITMAN_HARNESS_WORK_DIR` | workspaces de análisis (0700) | `$XDG_STATE_HOME/litman-harness/work` |

Sin `XDG_*` se usan `~/.config` y `~/.local/state`.

`litman login` (sólo CLI, interactivo) abre el flujo de escritorio
(`InstalledAppFlow.run_local_server(port=0)`) con el único scope `drive` y
guarda el token. `drive.file` no sirve: no abre por ID carpetas creadas fuera de
la app. Un token concedido con otro scope devuelve `oauth_scope_missing` y exige
repetir el login. Los tokens caducados con `refresh_token` se refrescan y
persisten automáticamente; sin token o sin refresco posible se devuelve
`oauth_login_required`.

## Operaciones

Todas devuelven el mismo sobre en ambos transportes:
`{"ok": true, "result": ...}` o `{"ok": false, "error": {"code", "message", "details"}}`.
Los argumentos se validan contra el `inputSchema` (obligatorios, tipos,
enumerados, sin propiedades extra) → `invalid_request`.

| Operación | Tipo | Efecto |
| --- | --- | --- |
| `identity` | consulta | cuenta activa |
| `diagnose` | consulta | adaptador, identidad, scopes, disponibilidad y contrato de `litman-core` instalado, proveedor fijado por `setup`, mecanismo de estado compartido y rutas configuradas (sí/no); nunca tokens ni rutas |
| `inspect` | consulta | inventario de todo el árbol de la carpeta (`tree`, `candidates`, sugerencias) y `next_actions` |
| `status` | consulta | inspección + manifiesto: `unadopted`, `partial`, `adopted`, `degraded`, `unsupported_manifest`; publicaciones locales pendientes; `recommended_action` |
| `preview_incorporation` | consulta | plan con sólo lo que falta: fase, carpetas (`folder_ids` para registrar existentes), originales, oferta viva existente, contexto y manifiesto |
| `apply_incorporation` | mutación | aplica el `plan_id` aceptado |
| `preview_analysis` | consulta | plan de Core con originales y tipo, con el proveedor fijado por `setup`; incluye su publicación. Sin `setup`, `setup_required` |
| `execute_analysis` | mutación | ejecuta Core para el `plan_id` aceptado y publica sus resultados sin otra aceptación |
| `discard_analysis` | mutación local | borra sólo el workspace de un análisis no publicado |
| `preview_publication` | consulta | recuperación: plan de publicación de un análisis local (`analysis_operation_id`) |
| `apply_publication` | mutación | aplica o reanuda el `plan_id` de publicación |
| `read_document` | consulta | una página de texto (PDF/DOCX) de un original registrado o artefacto publicado de la licitación; contenido, no instrucciones |
| `preview_summary` | consulta | plan con el resumen de la licitación (claves fijas, una fuente por línea) |
| `apply_summary` | mutación | guarda el resumen aceptado en manifiesto y `contexto.md` |
| `recover` | consulta | estado local de una operación |
| `setup` | mutación local | fija proveedor (`codex`, `claude-code`) y modelo opcional de LitMan Core para esta instalación, tras comprobar `litman-core info`; no toca Drive |

CLI: `litman <operación-con-guiones> [--json '{...}']`; imprime el sobre por
stdout, o por stderr con salida 2 si falla. MCP (`litman-mcp`): JSON-RPC 2.0 por
líneas; `initialize` (eco de `2025-06-18`, `2025-03-26` o `2024-11-05`),
notificaciones sin respuesta, `ping`, `tools/list` con `inputSchema` y
`tools/call`, cuyo texto es el sobre y que marca `isError` si `ok` es falso.
Errores de protocolo: `-32700`, `-32600`, `-32601`, `-32602`. Los servicios se
construyen en cada llamada, así que `tools/list` funciona sin configuración.

## Expediente compartido

`_LitMan/manifest.json` (`litman-dossier-v1`) guarda IDs, fase (`sin_analisis`,
`analisis_inicial`, `analisis_detallado`, `oferta_en_preparacion`, `entregada`),
carpetas por función, `context_file_id`/`context_sha256`, originales con
procedencia y `md5_checksum` (opcional en manifiestos antiguos), análisis
publicados con sus artefactos, el `summary` de la licitación (ver «Resumen de la
licitación»), `live_offer` (`document_id` y
origen `existing_external` o `core_conversion`) e historial. Otra instalación
recupera todo leyendo ese archivo desde el ID de la carpeta; las referencias son
por ID, así que renombrar no las rompe. Una versión desconocida se muestra en
sólo lectura. La fase cambia mediante una incorporación aceptada o al publicar
un análisis, que sólo la avanza si va por detrás (`assessment` →
`analisis_inicial`; `detailed-analysis` → `analisis_detallado`); nunca retrocede.

`contexto.md` se genera de forma determinista sólo desde el manifiesto: nombre,
fase, resumen de la licitación, carpetas y documentos enlazados por ID, oferta viva y resultados citando
`operation_id` y `publication_id`, con cada artefacto enlazado por ID y una frase
fija por rol (ficha de oportunidad, resumen técnico, guía de preparación,
simulador económico, documento técnico como borrador de oferta), sin depender
del contenido de Core. Cada actualización (a) lee el contexto y
compara su SHA-256 con `context_sha256`, (b) escribe el manifiesto y (c) escribe
el contexto con `update_if_version` usando la versión leída en (a). Si alguien
lo editó fuera de LitMan, la operación **no falla**: termina `succeeded`, el
manifiesto conserva el SHA anterior, `contexto.md` no se toca y el resultado
incluye `context_conflict` (`file_id`, `proposed_content`, `reason`); lo mismo
si (c) recibe `concurrent_change`. La salida explícita es
`preview_incorporation` con `overwrite_context: true` (válido aunque no haya
otros cambios): añade `replace_context`, que «sobrescribe ediciones externas»
sólo si el contenido sigue siendo el visto en la vista previa. Una operación
sólo se da por terminada cuando manifiesto y contexto están escritos o
resueltos; si se cae entre ambos, repetir la aceptación escribe el contexto
(la entrada de `history` con su `operation_id` prueba que el manifiesto ya se
escribió).

## Planes, estado compartido y recuperación

Cada `preview_*` guarda el plan en el almacén local ligado a la cuenta; `apply_*`
sólo acepta ese `plan_id` y rechaza planes de otra cuenta u obsoletos
(`stale_plan`; ver «Detección de cambios en Drive»). Toda
escritura en Drive (carpetas, subidas, conversión, manifiesto y contexto) pasa
por la capacidad de estado compartido (`create_if_absent`, `read`,
`update_if_version` que lanza `concurrent_change`):

- **OAuth** → `DriveSharedState` (`adapters/drive_state.py`). El smoke autorizado
  del 2026-10-15 demostró que Drive API v2 respeta `If-Match` en la subida de
  contenido (ETag vigente → 200, obsoleto → 412, ETag fuerte); v3 no expone ETag.
  `read` devuelve `(contenido, etag)` de una instantánea coherente (ETag v2 antes
  y después de bajar el contenido, hasta 3 intentos); `update_if_version` hace
  `PUT upload/drive/v2/files/{id}?uploadType=media` con `If-Match` y un 412 nunca
  sobrescribe. Ese ETag es la **única** versión del estado compartido: la
  incorporación detecta un manifiesto cambiado desde la vista previa por el
  SHA-256 de su contenido, nunca comparando la `version` v3 con el ETag.
  `create_if_absent` adopta el archivo con los marcadores de la acción, rechaza
  un nombre ya existente (`already_exists`) o lo crea (v3 multipart con
  marcadores). No es atómico entre operaciones distintas: dos `manifest.json`
  simultáneos aparecen después como `manifest_duplicated` y requieren reparación
  humana (riesgo aceptado). `diagnose` informa `shared_state.mechanism =
  drive_v2_if_match`.
- **Metadatos de desarrollo** → `UnavailableSharedState` (sólo lectura):
  `apply_incorporation` y `apply_publication` registran la operación como
  `planned` y devuelven `pending_concurrency_gate` sin escribir nada.

Cada recurso creado lleva `appProperties` `litman_operation_id` y
`litman_action_id`. Repetir una operación `succeeded` devuelve el resultado
registrado sin escribir. Tras un fallo a mitad (`operation_interrupted`, estado
`recoverable`), repetir la aceptación salta acciones completadas y, para las no
confirmadas, busca en su carpeta padre por esos marcadores: uno se adopta,
ninguno se crea y más de uno termina en `conflict`.

## Análisis, publicación y oferta viva

### Detección de cambios en Drive

La `version` de Drive no sirve para detectar cambios: en la prueba real la raíz
pasó de 8 a 9 sólo con abrirla y un PDF recién copiado cambió de versión
mientras Drive lo procesaba, lo que producía falsos `stale_plan`. Por eso:

- un original se identifica por su contenido: los planes de incorporación y de
  análisis guardan su `md5Checksum` (un original sin MD5 se rechaza en la vista
  previa con `missing_checksum`) y sólo es obsoleto si cambia ese MD5, va a la
  papelera o sale del árbol; `drive_version` se conserva como dato informativo;
- la raíz, las carpetas registradas y la oferta viva se comprueban por
  existencia, papelera y pertenencia (la oferta también por MIME y capacidad),
  nunca por versión;
- tras descargar, el MD5 de los bytes locales debe coincidir con el planificado
  («el original cambió durante la descarga» → `stale_plan`);
- el estado compartido se juzga por el SHA-256 del contenido y se protege con el
  ETag v2 de `read`.

### Contrato con Core

El harness depende **sólo del contrato público de la CLI** de Core, documentado
en [`docs/contracts.md`](../../docs/contracts.md) (claves de `config.toml`,
forma exacta del JSON de `run`/`info`, roles de artefacto, códigos de error y
política de versionado); no se repite aquí. El harness genera siempre la
plantilla mínima (sin `job.id`, `input.kind` ni `[publication]`: Core resuelve
`input.kind = "local"` y `publication.include_run_files = false` por defecto),
de modo que Core valida su propio run y deja en `local_path` sólo los
artefactos públicos, en plano. El harness no lee ningún archivo interno de Core
(`validation.json`, `generation_manifest.json`, salidas estructuradas); valida
el resultado por `role` (`analysis/results.py::REQUIRED_ROLES`), nunca por
nombre de archivo.

`execute_analysis` descarga sólo los originales planificados a un workspace
privado cuya carpeta de entrada se llama `<operation_id>` (un UUID4 válido para
el patrón de `job.id`), no `input`: como no se envía `job.id` explícito, Core lo
deriva del nombre de esa carpeta, y debe ser único por ejecución para que
`publication_id` también lo sea. Exige que `local_path` esté dentro del
`output` del workspace y que cada rol requerido por tipo de job aparezca
exactamente una vez, con su archivo presente y su SHA-256 verificado; un rol
desconocido, duplicado, ausente o con checksum distinto → `invalid_core_result`.
El resultado (rutas, SHA-256 y rol de cada artefacto, proveedor, versiones y
snapshot de entrada con MD5 y SHA-256) se registra en el almacén local bajo el
`operation_id` del análisis; sólo ese catálogo cerrado puede llegar a Drive. Un
fallo de Core conserva el workspace e informa su ruta; un éxito lo conserva
hasta publicar o descartar.

El proveedor (`codex` o `claude-code`) y el modelo opcional se fijan una vez por
instalación con `litman setup --json '{"provider": "...", "model"?: "..."}'`
(comprueba `litman-core info`, exige que el contrato coincida y que el
proveedor esté entre los que ofrece la instalación de Core, y guarda el ajuste
bajo `$XDG_CONFIG_HOME/litman-harness/settings.toml`, 0600 en directorio 0700).
`preview_analysis` sin `setup` devuelve `setup_required` con una
`recommended_action` hacia `setup`; cada plan de análisis guarda el proveedor
(y modelo) vigente en ese momento, así que cambiar el `setup` después no altera
la ejecución de un plan ya aceptado. Core usa por defecto el modelo
`gpt-5.6-luna` con Codex (el anterior, `gpt-5.5`, lo rechaza una cuenta
ChatGPT) y `claude-sonnet-5` con Claude Code; `setup` permite fijar otro modelo
explícitamente.

`preview_publication` exige expediente adoptado y su carpeta de fase registrada,
y vuelve a comprobar los hashes locales. Planifica una carpeta
`AAAA-MM-DD <publication_id>` bajo `Analisis inicial`/`Analisis detallado`, una
subida por artefacto, la conversión del DOCX técnico a Google Doc en `Oferta`
(sólo análisis detallado sin oferta viva registrada; nunca la reemplaza) y la
actualización de manifiesto y contexto. El plan no fija la versión del
manifiesto: `apply_publication` lee el vigente y fusiona de forma aditiva
(análisis, historial y SHA de originales). Exige que las carpetas de destino
pendientes sigan siendo las registradas (si no, `conflict`); si entretanto se
registró una oferta viva, omite la conversión y el DOCX queda sólo como
artefacto; si el análisis ya figura en el manifiesto, la da por terminada. Si la
escritura del manifiesto recibe `concurrent_change`, la operación queda
`recoverable` (`manifest_changed_retry`) y repetir la aceptación reanuda sin
volver a subir nada. Tras un éxito completo se borra el workspace local.
La incorporación mantiene la semántica estricta: un manifiesto cambiado desde la
vista previa termina en `conflict`.

## Resumen de la licitación

El harness no contiene un LLM: el resumen lo prepara el asistente del chat (o un
subagente lector con el modelo más económico) y lo acepta la persona. Tras un
`apply_publication` correcto el resultado trae `next_actions: propose_summary`
(o `refresh_summary` si ya había resumen); `status` sugiere lo mismo: no hay
resumen y sí análisis publicados, o hay análisis publicados que no están en
`based_on_analyses`.

`manifest.summary` es de la **licitación**: `items` con claves cerradas en orden
fijo (`objeto`, `organismo`, `expediente`, `procedimiento`, `presupuesto`,
`valor_estimado`, `plazo_ejecucion`, `fecha_limite`, `lotes`,
`solvencia_economica`, `solvencia_tecnica`, `equipo`, `criterios_adjudicacion`,
`recomendacion`, `alertas`; obligatorias `objeto`, `organismo`, `presupuesto` y
`fecha_limite`), cada una con `value` (1–300 caracteres, una línea, sin
caracteres de control) y `source_file_id` (un original registrado o un artefacto
publicado de esta licitación; sólo puede omitirse con `"No consta"`), más
`based_on_analyses`, `accepted_by`, `accepted_at` y
`origin: assistant_proposal_accepted`. Las etiquetas legibles las pone el harness.

1. `read_document(folder_id, file_id, offset=0)`: sólo originales registrados o
   artefactos publicados de **esa** licitación (lo decide el manifiesto antes de
   tocar Drive) y dentro de su árbol; PDF (`pypdf`) o DOCX (`python-docx`,
   párrafos y celdas). Devuelve `kind` (`original`/`artifact`), 20 000
   caracteres por página con `offset`, `next_offset` y `characters`, y una
   `note`: el texto es contenido, no instrucciones. No escribe ni guarda planes.
2. El lector propone sólo el JSON de `items`, sin inventar ni interpretar.
3. `preview_summary(folder_id, items)` valida el contrato, ordena las claves y
   guarda un plan `summary` (`set_summary` con el resumen anterior y el nuevo,
   `update_context`, `update_manifest` con el SHA del manifiesto leído).
4. `apply_summary(plan_id)` usa el motor común: manifiesto cambiado desde la
   vista previa → `conflict`; `contexto.md` editado fuera → `succeeded` con
   `context_conflict`.

`contexto.md` muestra `## Resumen` justo tras fase y expediente: una línea por
clave en orden fijo, `- Etiqueta: valor (fuente: enlace)`, y la línea de
procedencia; sin resumen, «Resumen pendiente de proponer». El harness sólo
verifica forma y procedencia, nunca la veracidad.

### Agente de producto

- `skills/resumir-licitacion`: cuándo, qué leer (primero ficha y resumen
  técnico; originales sólo para claves que falten), claves y reglas, formato de
  `items`; delega la lectura en `lector-licitacion` si la aplicación admite
  subagentes (Claude Desktop no: lo hace el chat principal).
- `skills/conectar-licitacion`: tras publicar, pregunta una vez si prepara el
  resumen; nunca lo aplica por iniciativa propia.
- `claude/agents/lector-licitacion.md`: `model: haiku`, `tools:` sólo
  `mcp__litman__status` y `mcp__litman__read_document` (servidor MCP `litman`).
- `codex/agents/lector-licitacion.toml`: `gpt-5.6-luna`,
  `model_reasoning_effort = "low"`, `sandbox_mode = "read-only"`, instrucciones
  de usar sólo `status` y `read_document`.

Prueba manual (la instalación automática está pendiente): registrar `litman-mcp`
como servidor MCP `litman`; en Claude Code copiar el `.md` a
`.claude/agents/` (proyecto) o `~/.claude/agents/` y las skills a
`.claude/skills/`; en Codex copiar el `.toml` a su directorio de agentes y las
skills al de skills. Tras publicar un análisis en la carpeta de prueba, aceptar
la sugerencia y comprobar que el subagente sólo lee y que `contexto.md` muestra
el resumen con sus fuentes.

## Recorrido guiado

El asistente sigue un recorrido fijo: organizar (estructura y originales) →
análisis inicial (con publicación) → resumen → ¿análisis detallado? (con
publicación y oferta viva) → refrescar el resumen → la persona decide.

- **Árbol completo.** `inspect`/`status` recorren en anchura todo el árbol bajo
  la raíz (`dossier/tree.py`: sólo `children` de carpetas del árbol, nunca
  búsquedas globales, sin descender a `_LitMan`, como máximo 2 000 elementos →
  `tree_truncated`). `tree` lleva `path` relativo y `depth`; `children` sigue
  siendo el primer nivel. Candidatos: `originals` (archivos admitidos por el
  análisis no registrados y fuera de carpetas registradas de resultados,
  oferta, entregas, interno o `_LitMan`, y fuera de resultados previos de Core),
  `offer` (Google Docs no registrados), `folders` (`{id, path}`, sin `_LitMan`),
  `previous_core_outputs` (carpetas escritas por el publicador Drive de Core,
  reconocidas por `appProperties.publication_contract`:
  `{folder_id, path, job_type, files[{id, path}]}`; sus archivos nunca se
  proponen como pliegos ni se registran solos, y `next_actions` lo indica con
  `review_existing_analysis`; un archivo suelto sin esa marca, como una
  `ficha_oportunidad.pdf` en la raíz, sigue siendo candidato y decide la
  persona) y `suggested_folder_ids`: carpetas de primer nivel
  cuyo nombre coincide, sin mayúsculas ni acentos, con el de una función
  estándar y que no están registradas. Es sólo una sugerencia: se aplica si la
  persona la confirma y llega como `folder_ids` a `preview_incorporation`.
- **`recommended_action`** (`dossier/recommendation.py`, función pura): primera
  que aplique de `review_manifest` → `incorporate` (sin manifiesto o sin
  originales registrados; con originales registrados, los candidatos sin
  registrar no bloquean el recorrido y quedan como opción `incorporate` en
  `next_actions`) →
  `publish_analysis` (análisis local pendiente) → `run_assessment` →
  `propose_summary`/`refresh_summary` → `decide_detailed_analysis` (pregunta de
  negocio) → `null` (preguntar a la persona). Lleva `kind`, `reason`, `tool` y
  `arguments`. La devuelven `status`, `apply_incorporation`,
  `execute_analysis`, `apply_publication` y `apply_summary` (estas últimas sobre
  el manifiesto resultante).
- **Análisis con publicación.** Con el ensamblado normal, `preview_analysis`
  exige expediente adoptado y las carpetas necesarias (fase; `Oferta` si es
  detallado sin oferta viva) **antes** de ejecutar Core, y añade al plan
  `publish_results`, `convert_live_offer` si procede, `set_phase` si la fase va
  por detrás, `update_context` y `update_manifest`. `execute_analysis` ejecuta
  Core y publica con `PublicationService` sin otra aceptación; el plan de
  publicación queda enlazado en el registro del análisis. Si la publicación
  falla, la respuesta trae `publication.status = failed` y una recomendación de
  repetir `execute_analysis` con el mismo `plan_id`, que reanuda sin volver a
  ejecutar Core ni a subir lo ya subido (`apply_publication` del plan enlazado
  también sirve).
- **Tiempo máximo de las herramientas MCP.** `execute_analysis` dura minutos.
  En Codex amplíe el límite del servidor (por defecto 60 s) en
  `~/.codex/config.toml`: `[mcp_servers.litman]` con `tool_timeout_sec = 1800`.
  En Claude Code, `MCP_TOOL_TIMEOUT` (milisegundos). Si un cliente no lo
  permite, una ejecución en segundo plano con sondeo es candidata para la
  tarea de instalación.

## Validación humana pendiente

Estos pasos requieren autorización explícita, una carpeta de prueba y cuentas
reales; ningún test con dobles los sustituye. Hecho el 2026-10-15 con la cuenta
A en una carpeta de prueba: precondición atómica (v2 `If-Match`; el script de
smoke se retiró), incorporación, conflicto de contexto y `overwrite_context`,
análisis inicial y detallado con Codex, publicación de ambos con oferta viva
convertida a un único Google Doc, reintentos `replayed` sin duplicados y
resumen propuesto por un lector Haiku (con la CLI) y aplicado; la revisión
visual del Google Doc de la oferta convertida fue correcta. Pendiente:

1. **Segunda cuenta.** Con el cliente OAuth corporativo (scope `drive`), ejecutar
   `litman login` en otra instalación con otra cuenta y comprobar con
   `diagnose`, `inspect` y `status` que recupera el expediente por ID.
2. **Descubrimiento MCP y subagente.** Registrar `litman-mcp`, las skills y
   `lector-licitacion` en Codex App, Claude Desktop y Claude Code (la
   instalación automática está pendiente), comprobar que aparecen las
   herramientas con su descripción, que `status` responde y que el subagente
   propone el resumen sólo leyendo vía MCP. Smoke local previo,
   con un JSON de metadatos temporal en `LITMAN_HARNESS_METADATA`: enviar por
   stdin `initialize`, `notifications/initialized`, `tools/list` y un
   `tools/call` de `inspect`.
