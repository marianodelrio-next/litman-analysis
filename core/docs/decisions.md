# Durable Technical Decisions

## Development-agent system

- The former `research-design` / `implement` skills, their development agents,
  and `.agent-work/<task>/` task folders were retired when the Software Factory
  was adopted on 2026-10-19. The local task folders were later removed at the
  person's request; new Factory state is managed only through `swfactory`.
- The current development workflow lives in the root `AGENTS.md`, Factory
  skills under `.agents/` and `.claude/`, and `.factory/config.toml`. It remains
  separate from the product pipeline and its Codex CLI. Authorized direct
  changes may still proceed without a Factory task.
- Durable architecture and product decisions remain in the relevant package
  documentation; the [codebase map](../../docs/codebase-map.md) is the navigation
  index.

## Application namespace and Docker boundary

- `litman_core` is the only Core application package (the `litman-harness` distribution is a separate client; see «Harness de expediente») and owns CLI, orchestration, domain, pipelines, infrastructure, generation, configuration, and packaged resources.
- The former alternate Python package is removed rather than retained as a compatibility implementation.
- `litman-core` is Core's only public entry point. Docker invokes the same CLI and does not add a package worker entry point.
- Docker remains the external distribution and isolation boundary; domain and pipelines do not select or branch on runtime.
- Local development and local wheel consumption are documented as separate
  flows (`deployment/local-dev/` and `deployment/local-install/`). The wheel
  flow takes its workspace and runs paths from `config.toml` and the
  environment. Docker continues to install a built wheel in its
  isolated runtime.

## Technical summary artifact contract

- `resumen_tecnico.docx` is a single compact technical brief generated
  deterministically from the detailed-analysis dossier. Its stable structure is
  one title followed by five numbered sections: context, objectives, phases and
  deliverables, technologies and resources, and key aspects.
- The artifact preserves critical requirements, criteria, phase deliverables,
  and explicit empty states; it may abbreviate descriptions deterministically
  but must not invent content or add a separate cover/detail section.
- The generator contract version is bumped when this structure changes.

## Bid preparation guide artifact contract

- `guia_preparacion_oferta.docx` remains a deterministic operational guide
  generated from the persisted dossier, with the canonical ID
  `bid-preparation-guide`.
- Its compact body has five fixed numbered sections: context, documents to
  submit, offer-preparation requirements, award criteria, and pending checks.
  The guide keeps operational requirements, rules, consequences, criteria, and
  pending actions, while omitting the technical-summary content and the
  evidence appendix; traceability remains in the dossier and persisted
  analysis results.
- Missing format data is grouped into one `No consta` notice, and unknown
  values use that same convention. The generator contract version is bumped
  when this structure changes.

## Harness de expediente

- `litman-harness` es una distribución separada: no importa `litman_core` y lo
  ejecuta sólo como proceso `litman-core run` con configuración local, nunca con
  `output.google_drive_folder_id`. Core no conoce el harness.
- Sólo OAuth personal de escritorio, con el scope `drive` (aplicación interna);
  nunca cuenta de servicio. `drive.file` se descartó tras la prueba real: no
  permite abrir por ID carpetas de la unidad compartida no creadas por la app.
  Google concede como máximo el acceso de la propia persona y el harness limita
  cada operación al árbol de la carpeta conectada.
  Token, cliente OAuth, planes y workspaces viven fuera del clon y nunca se
  aceptan por argumentos, stdio, manifiesto ni contexto.
- El ID de la carpeta de la licitación es el único punto de entrada; la
  pertenencia se comprueba por la cadena de padres hasta esa carpeta, sin
  búsquedas globales.
- Las mutaciones son preview/apply: `apply_*` sólo acepta un `plan_id` guardado
  localmente para la misma cuenta; el agente nunca envía el plan.
- `_LitMan/manifest.json` v1 es la fuente de verdad; `contexto.md` se genera de
  forma determinista desde él y no es instructivo. Las ediciones ajenas de
  `contexto.md` no se sobrescriben salvo un plan con `overwrite_context`
  aceptado.
- Estado compartido: con OAuth toda escritura pasa por `DriveSharedState`, que
  actualiza con Drive API v2 `If-Match` (412 → `concurrent_change`, nunca
  sobrescribe), demostrado en real; v3 no expone ETag. El ETag v2 de `read` es
  la única versión del estado compartido; una incorporación detecta un
  manifiesto cambiado por su SHA-256. Create-if-absent no es atómico entre
  operaciones: un `manifest.json` duplicado se detecta como
  `manifest_duplicated` y exige reparación humana (riesgo aceptado). Adaptadores
  de sólo lectura siguen devolviendo `pending_concurrency_gate`.
- Los cambios en Drive se detectan por el MD5 del contenido de los originales y
  por existencia/papelera/pertenencia de raíz, carpetas y oferta; nunca por la
  `version` de Drive, que cambia sin cambios reales.
- El harness sólo usa el contrato público de la CLI de Core (código de salida y
  JSON de stdout con `artifacts[{name, uri, checksum}]`, `include_run_files=false`)
  y no lee archivos internos del run.
- Los recursos creados llevan `appProperties` (`litman_operation_id`,
  `litman_action_id`) para reintentos idempotentes.
- La fase del expediente es un conjunto cerrado y sólo cambia por un plan
  aceptado por la persona: una incorporación o un análisis con publicación
  (que sólo la hace avanzar, nunca retroceder).
- Recorrido guiado: el siguiente paso (`recommended_action`) lo calcula el
  código de forma determinista con un orden fijo (revisar manifiesto →
  organizar → publicar análisis pendiente → análisis inicial → resumen →
  ¿análisis detallado? → nada); la skill sólo lo sigue y pide aceptación.
  Análisis inicial y detallado son pasos distintos; el detallado es una
  decisión de negocio que se pregunta, nunca un paso automático.
- El plan de análisis incluye su publicación: una sola aceptación ejecuta Core
  y publica reutilizando `PublicationService`; si la publicación falla, se
  reanuda con el mismo plan sin repetir Core. Preview/apply de publicación se
  mantiene para recuperación.
- `inspect`/`status` inventarían todo el árbol bajo el ID dado (sólo
  `children`, sin `_LitMan`, con límite y aviso de truncado). Las sugerencias
  por nombre de carpeta sólo se aplican si la persona las confirma.
- Los resultados previos de Core en Drive se reconocen por su marca
  (`appProperties.publication_contract`), nunca por el nombre, y no se proponen
  como pliegos ni se registran solos.
- Hay una única oferta viva (`live_offer.document_id`); un reanálisis nunca la
  reemplaza ni crea otra.
- El resumen es uno por licitación (`manifest.summary`): claves cerradas en
  orden fijo y fuente por línea (originales registrados o artefactos
  publicados). Lo propone el agente, opcionalmente delegando la lectura en un
  subagente de sólo lectura con el modelo más económico, y sólo se guarda tras
  `preview_summary`/`apply_summary` aceptados por la persona; el harness sigue
  siendo el único que escribe.
- Las skills y subagentes de producto viven en `harness/agent/`, separados de
  la configuración de desarrollo en `.agents/`.
