# LitMan Core + LitMan Harness — Diseño objetivo y plan de evolución

> **Estado:** propuesta de arquitectura para revisión, **no implementada**.  
> **Fecha:** 9 de octubre de 2026  
> **Ámbito:** evolución del repositorio actual hacia `LitMan Core` y `LitMan Harness`, con distribución Docker y ejecución local basada en Codex. La integración con una aplicación cloud queda fuera de este diseño.  
> **Referencia de partida:** arquitectura, mapa del repositorio y decisiones compartidas en la conversación. Las rutas y contratos deberán comprobarse contra el código antes de modificarlos.

## 1. Objetivo

Convertir el LitMan Analysis actual en **un único paquete Python, LitMan Core**, que conserve el análisis de licitaciones y pueda ejecutarse mediante dos modalidades:

1. **Distribución Docker:** imagen con LitMan Core instalado, para conservar la ejecución aislada actual.
2. **LitMan Harness:** plantilla de instrucciones, skills, workspace y comandos que utiliza una instalación local de LitMan Core desde **Codex App**.

Google Drive conecta ambas modalidades: aloja expedientes y documentos compartidos; cada usuario dispone de un workspace local independiente. **El repositorio es único** y se generan las mismas salidas contractuales a partir de una misma versión del Core.

### Principios no negociables

- **Un Core, dos modalidades.** Docker no debe formar parte de la lógica del motor; es su empaquetado y aislamiento. LitMan Harness es la interfaz local que invoca el mismo Core.
- **Sin reescritura masiva.** Mantener `JobRunner`, pipelines, schemas, validaciones, generación y adaptadores actuales; mover directorios solo si existe necesidad demostrada.
- **Separación de agentes.** El Codex CLI empleado *dentro* de los pipelines no es el Codex App que *orquesta* el trabajo de negocio, ni los agentes que desarrollan el repositorio.
- **Análisis oficial verificable.** Conservación de contratos, evidencias, lineage y generación determinista de los artefactos actuales.
- **Sin clonación del repositorio por negocio.** La instalación se efectúa con un artefacto publicado; no requiere Git ni Docker.
- **Colaboración sin pérdida de datos.** Ningún push sobrescribe de forma silenciosa archivos modificados por otras personas.
- **Actualizaciones seguras.** Las nuevas versiones del Core y de las skills oficiales no borran expedientes ni skills personales.

## 2. Punto de partida: qué tenemos

El proyecto es un servicio Python 3.11, ubicado actualmente en `src/litman_analysis/`. Como parte de la consolidación de nombre, LitMan Core se migrará a `src/litman_core/`.

| Elemento existente | Responsabilidad actual | Decisión |
| --- | --- | --- |
| `application/`, `domain/` | Jobs, reglas y modelos | Conservar |
| `execution/job_runner.py` | Orquestación canónica | Conservar; servir a las dos instalaciones |
| `pipelines/assessment/` | Evaluación inicial | Conservar |
| `pipelines/detailed_analysis/` | Análisis detallado | Conservar |
| `infrastructure/llm/` | Integración con Codex CLI | Conservar inicialmente |
| `infrastructure/storage/` | Fuentes/publicación local y Drive | Reutilizar y extender cuidadosamente |
| `infrastructure/documents/` | Inventario y normalización | Conservar |
| `generation/` y `resources/` | Documentos, plantillas, prompts y schemas | Conservar; añadir salida de contexto |
| `cli.py` | CLI pública `litman-analysis`, actualmente ligada a Docker | Añadir ejecución nativa sin romper `run`, `assess` ni `analyze` |
| `worker.py` | Entrada de ejecución en contenedor | Conservar durante migración |
| `execution/container_launcher.py` | Lanzamiento Docker desde host para la CLI pública | Mantenerlo como compatibilidad; dejar de imponerlo a la ejecución nativa |
| `AGENTS.md`, `.agents/`, `.codex/` | Harness de **desarrollo** | Aislar completamente del harness de negocio |

**Contrato actual que debemos respetar durante la migración:** la CLI host (`litman-analysis`) valida y lanza Docker mediante `ContainerJobLauncher`; el worker (`litman-analysis-worker`) materializa fuentes locales o Drive, construye un `DocumentBundle`, ejecuta `assessment` o `detailed-analysis`, valida resultados y publica. Estos nombres se retirarán cuando exista la única CLI pública `litman-core`. `assessment` publica hoy solo `ficha_oportunidad.pdf` en Drive. El catálogo detallado permitido contiene cuatro artefactos y la entrega por defecto los publica todos; las opciones actuales pueden seleccionar subconjuntos en otros contextos, por lo que el diseño debe fijar qué catálogo será obligatorio para la publicación oficial. Cambiar estas publicaciones requiere diseño de compatibilidad explícito.

## 3. Arquitectura objetivo

```text
                         REPOSITORIO ÚNICO (main)
                                   |
                        LitMan Core · Python
                 JobRunner + pipelines + Codex CLI
              Drive + validación + generación + contexto
                                   |
                  build/release misma versión del Core
                         /                     \
                        /                       \
             DISTRIBUCIÓN DOCKER          LITMAN HARNESS
             Worker actual                 Core Python + skills
             + runtime aislado              Codex App + workspace
                        |                       |
                 Drive / local          Workspace por usuario
```

**Nota esencial:** El Core no contiene lógica de selección `native`/`docker`. `JobRunner` ejecuta el job; la CLI nativa lo invoca directamente y la CLI/worker Docker lo invocan dentro del contenedor. La distinción está en la capa de entrada y empaquetado, no en pipelines distintos.

### Tres piezas, con responsabilidades distintas

- **LitMan Core:** paquete Python responsable de ejecutar jobs, pipelines, validaciones, generación de artefactos, persistencia local/Drive y CLI. No conoce si se ejecuta en local o dentro de Docker.
- **LitMan Harness:** capa de uso formada por instrucciones, skills, workspace y comandos. Invoca LitMan Core y no contiene una segunda implementación de los pipelines.
- **Distribución Docker:** empaquetado del Core con sus dependencias de sistema, aislamiento y entrypoint para la ejecución en contenedor.

No necesitamos tres ramas de Git ni tres implementaciones de los pipelines.

### Nombres y alcance

- **LitMan Core** es el producto técnico: el paquete Python que ejecuta análisis y genera las salidas del expediente.
- **LitMan Harness** es la capa de uso: `AGENTS.md`, skills, comandos y estructura de workspace que permiten trabajar con Core desde Codex App.
- **Distribución** significa cómo se entrega el software: una wheel/paquete local o una imagen Docker.
- **Ejecución** significa dónde corre: directamente en Python mediante el Harness o dentro de un contenedor Docker.
- **Despliegue** significa instalar y arrancar una distribución en un entorno concreto. En este diseño solo se contempla la instalación local del Harness y la ejecución Docker actual; no se diseña todavía una plataforma cloud.

LitMan Harness no es otro motor ni otra copia de los pipelines: es una interfaz y un conjunto de herramientas que invoca LitMan Core.

## 4. Estructura: repositorio, distribución y workspace

Este punto separa tres árboles diferentes. No son tres proyectos ni tres motores:

1. **Repositorio:** contiene el código fuente, tests y materiales para construir las distribuciones.
2. **Paquete de distribución:** contiene LitMan Core y una plantilla del Harness para instalarlo en otro equipo.
3. **Workspace instalado:** contiene los expedientes y personalizaciones del usuario; no contiene el repositorio ni los tests.

### 4.1 Repositorio de desarrollo

La migración de `src/litman_analysis/` a `src/litman_core/` forma parte de la fase 1. Este árbol es el único que se versiona como repositorio:

```text
litman-analysis/
├── src/litman_core/                 # LITMAN CORE: paquete Python único
│   ├── application/                # EXISTE: contratos y casos de uso
│   ├── domain/                     # EXISTE: reglas y validaciones
│   ├── pipelines/                  # EXISTE: assessment / detailed
│   ├── generation/                 # EXISTE: documentos; añadir contexto
│   ├── infrastructure/             # EXISTE: Codex, documentos, Drive
│   ├── execution/
│   │   ├── job_runner.py           # EXISTE: orquestador
│   │   └── container_launcher.py   # LEGACY: host->Docker (transitorio)
│   ├── workspace/                  # NUEVO: contratos/operaciones de workspace
│   ├── resources/                  # EXISTE: recursos versionados
│   ├── cli.py                      # ADAPTAR sin romper contratos
│   └── worker.py                   # EXISTE: entrypoint de contenedor
│
├── harness/                        # PLANTILLA: LitMan Harness
│   ├── AGENTS.md
│   ├── .agents/skills/
│   │   ├── litman-listar-licitaciones/SKILL.md
│   │   └── litman-analizar-licitacion/SKILL.md
│   └── templates/                  # Workspace, contexto, progreso
│
├── scripts/                        # NUEVO: setup, checks, releases
│   ├── setup-dev.sh
│   ├── build-harness.sh
│   ├── check-harness.sh
│   └── build-docker.sh
├── .github/workflows/              # NUEVO: tests y releases
├── tests/                          # EXISTE + nuevos contratos
├── docs/                           # EXISTE + nueva arquitectura
├── Dockerfile                      # EXISTE: distribución Docker de LitMan Core
├── pyproject.toml                  # EXISTE: paquete distribuible de LitMan Core
├── uv.lock                         # EXISTE; mantener sincronizado
├── AGENTS.md                       # Harness de DESARROLLO
├── .agents/                        # Skills de DESARROLLO
└── .codex/                         # Configuración de DESARROLLO
```

`AGENTS.md`, `.agents/` y `.codex/` en la raíz son exclusivamente del **harness de desarrollo del repositorio**. No se incluyen en la instalación del usuario.

### 4.2 Paquete de distribución de LitMan Harness

`build-harness.sh` construye un paquete instalable, no una copia del repositorio:

```text
litman-harness-<version>/
├── core/                       # wheel instalable de LitMan Core
├── harness/
│   ├── AGENTS.md               # instrucciones de negocio
│   ├── .agents/skills/         # skills oficiales
│   └── templates/              # plantillas de workspace
├── install/                    # setup y checks
└── VERSION
```

No incluye el código fuente del repositorio, `.codex/`, `.agent-work/`, tests, Dockerfile ni skills de desarrollo. El instalador puede crear un workspace separado y registrar la versión instalada.

### 4.3 Workspace instalado del usuario

El usuario trabaja en un directorio creado por el instalador. Este árbol contiene datos y configuración local, no el repositorio:

```text
LitMan/
├── AGENTS.md                   # reglas del LitMan Harness
├── .agents/skills/             # oficiales + personales
├── .litman/                    # configuración y manifest local
└── expedientes/
    └── exp-XX/
        ├── analisis-<timestamp>/
        │   ├── context.md
        │   ├── analisis-inicial/
        │   │   └── ficha_oportunidad.pdf
        │   └── analisis-detallado/ # aparece tras detailed-analysis
        ├── PROGRESS.md
        ├── fuentes/
        └── trabajo/
```

El workspace no contiene `src/`, `tests/`, `Dockerfile` ni `.codex/`. LitMan Harness invoca el LitMan Core instalado en el entorno Python y lee/escribe este workspace mediante contratos explícitos.

## 5. Plan por fases y tareas

### Fase 0 — Contratos y pruebas de referencia

**Objetivo:** establecer qué no se puede romper antes de desacoplar la ejecución.

**Tareas**

- [ ] Revisar `AGENTS.md`, mapa del código, arquitectura y decisiones; inspeccionar las implementaciones reales.
- [ ] Documentar los comandos públicos actuales (`litman-analysis run|assess|analyze` y `litman-analysis-worker run|preflight`) y diseñar la migración a una única CLI pública `litman-core`; distinguir CLI de transición, CLI final y worker interno.
- [ ] Registrar salidas y comportamiento de ambas pipelines con fixtures: artefactos, manifests, hashes, evidencias y nombres de publicación.
- [ ] Capturar la política actual de recursos, autenticación y permisos de Codex dentro de Docker.
- [ ] Definir un test de equivalencia para ejecuciones local y contenedor sin depender de igualdad byte a byte de resultados LLM no deterministas.

**Aceptación:** existe una línea base ejecutable con pruebas que detectan cambios no autorizados en contratos y publicaciones. No se han alterado pipelines.

### Fase 1 — Consolidar LitMan Core como paquete Python autónomo

**Objetivo:** ejecutar los dos pipelines desde una instalación Python **sin tener que iniciar Docker**, manteniendo la CLI Docker actual como compatibilidad.

**Tareas**

- [ ] Confirmar que `JobRunner` puede invocarse fuera del contenedor con los mismos contratos de job; no existe actualmente un “servicio de aplicación” separado.
- [ ] Exponer una única CLI pública `litman-core` para ejecutar jobs directamente con `JobRunner`; retirar progresivamente `litman-analysis` y `litman-analysis-worker` cuando la compatibilidad esté verificada.
- [ ] Separar configuración propia del entorno (rutas, secreto, autenticación, directorios de trabajo) de las reglas de análisis.
- [ ] Migrar el namespace Python de `litman_analysis` a `litman_core`: mover el paquete, actualizar imports internos, entry points, tests, Docker, recursos y documentación; mantener una estrategia de compatibilidad para instalaciones existentes durante la transición.
- [ ] Validar el empaquetado ya existente en `pyproject.toml` y asegurar que prompts, reglas, schemas y plantillas **se incluyen y resuelven desde una wheel instalada**.
- [ ] Documentar que el Core necesita dependencias externas de runtime; su contrato y verificación se definirán en la fase 2, no dentro de la lógica de los pipelines.
- [ ] Mantener temporalmente los comandos de Docker existentes como capa compatible mientras se migra el flujo; no crear un nuevo `NativeJobLauncher` si bastan una CLI nativa y la invocación directa de `JobRunner`.
- [ ] Añadir pruebas de instalación en un entorno limpio y ejecución local con fixtures.

**Aceptación:** un entorno Python limpio instala LitMan Core desde `src/litman_core`, localiza todos los recursos y ejecuta `assessment` y `detailed-analysis` sin Docker; las pruebas de contenedor continúan pasando; las dos entradas públicas conservan sus contratos y no quedan imports productivos bajo `litman_analysis` salvo compatibilidad explícita.

> **Decisión de interfaz:** se definirá el nombre final de la CLI (`litman`, `litman-analysis` u otro) al revisar compatibilidad. Los comandos de las fases siguientes son **ilustrativos**, no contratos implementados.

### Fase 2 — Contratos de runtime y distribuciones

**Objetivo:** separar el paquete LitMan Core de las formas concretas de instalarlo y ejecutarlo.

#### Fase 2A — Contrato de runtime del Core

- [ ] Generar una wheel versionada del Core (`uv build`) y validar instalación/importación fuera del árbol de código.
- [ ] Declarar las dependencias externas necesarias para ejecutar el Core: Codex CLI, Chromium para PDF, Node/npm si el Codex CLI lo requiere, ripgrep y fuentes/utilidades necesarias.
- [ ] Elegir versiones fijadas o rangos compatibles y proporcionar una instalación local sencilla y reproducible de esas dependencias, con instrucciones y comprobación automática; no exigir que el usuario configure manualmente cada binario sin guía.
- [ ] Definir un contrato de runtime verificable: versiones mínimas, binarios requeridos, variables de entorno, autenticación, permisos de filesystem y acceso a Drive.
- [ ] Crear un check determinista que valide ese contrato sin imprimir secretos.
- [ ] Separar dependencias de desarrollo de las dependencias necesarias para ejecutar LitMan Core.

**Aceptación:** una instalación Python limpia puede validar si el entorno tiene todo lo necesario para ejecutar LitMan Core, sin depender de Docker.

#### Fase 2B — Distribución Docker

- [ ] Adaptar `Dockerfile` para instalar la wheel de LitMan Core y las dependencias de sistema declaradas en el contrato de runtime.
- [ ] Conservar `litman-analysis-worker` y el aislamiento actual mientras exista compatibilidad pendiente.
- [ ] Mantener Docker como empaquetado y entorno de ejecución; no añadir lógica `--runtime docker/native` a pipelines ni al dominio.
- [ ] Ejecutar smoke tests del mismo job fixture en wheel local e imagen Docker, comparando contratos, validaciones y catálogo de salida.

**Aceptación:** la imagen Docker ejecuta la misma versión de LitMan Core que la instalación local y conserva los contratos actuales del worker.

#### Fase 2C — Distribución LitMan Harness

- [ ] Construir el paquete de LitMan Harness: wheel/Core, plantilla de workspace, skills, instrucciones y comandos de setup/verificación.
- [ ] Verificar que el Harness no contiene `.codex/`, `.agent-work/`, tests, Dockerfile ni skills de desarrollo.
- [ ] Establecer compatibilidad versionada entre Core, recursos y Harness.
- [ ] Verificar instalación limpia, autenticación, herramientas auxiliares y ejecución de un job fixture desde el Harness.
- [ ] Mantener para Drive la autenticación actual mediante cuenta de servicio, configurada por usuario y referenciada por `GOOGLE_APPLICATION_CREDENTIALS`; no introducir credenciales compartidas dentro del paquete.

**Aceptación:** LitMan Harness invoca una instalación real de LitMan Core y no contiene una segunda implementación del motor.

### Fase 3 — Contrato de salida de expediente y contexto

**Objetivo:** definir la salida visible y estable de cada expediente antes de construir el workspace y el harness. Los runs internos son temporales y no forman parte del contrato de negocio.

**Tareas**

- [ ] Establecer como contrato lógico para cada expediente:
  ```text
  exp-XX/
├── analisis-<timestamp>/
│   ├── context.md
│   ├── analisis-inicial/
│   │   └── ficha_oportunidad.pdf
│   └── analisis-detallado/
│       ├── dossier.json
│       ├── resumen_tecnico.docx
│       ├── guia_preparacion_oferta.docx
│       ├── propuesta_tecnica.docx
│       └── simulador_economico.xlsx

- [ ] Hacer que `assessment` genere obligatoriamente `analisis-<timestamp>/analisis-inicial/ficha_oportunidad.pdf` y `analisis-<timestamp>/context.md` inicial. No debe generar todavía un dossier detallado.
- [ ] Hacer que `detailed-analysis` genere obligatoriamente `analisis-<timestamp>/analisis-detallado/` y `analisis-<timestamp>/context.md` con el contexto ampliado. No debe modificar ejecuciones anteriores.
- [ ] Definir `context.md` como el único contexto vigente del expediente: resumen operativo y mapa con objeto, requisitos críticos, riesgos, preguntas abiertas, estado del análisis, rutas de artefactos y referencias a evidencias.
- [ ] Generar `context.md` determinísticamente a partir de resultados validados, salvo justificación explícita de un paso LLM.
- [ ] Registrar en el contexto la etapa que lo generó, versión del Core/recursos, fuentes utilizadas y fecha; el detallado debe indicar que amplía el contexto inicial.
- [ ] Separar el contexto oficial generado por Core de `PROGRESS.md`, que recogerá decisiones y cambios posteriores del usuario/harness.
- [ ] Permitir elegir el destino de cada ejecución: local o Google Drive. La estructura lógica será la misma; solo cambiarán el mecanismo de escritura, publicación y sincronización.
- [ ] Añadir tests de contrato de árbol, nombres, contenido, hashes, trazabilidad y regeneración.

**Aceptación:** cada ejecución crea una carpeta `analisis-<timestamp>` identificable; assessment deja en ella la ficha inicial y `context.md`, mientras detailed-analysis deja sus documentos y el contexto ampliado; ninguna etapa publica runs internos, logs o temporales.

### Fase 3A — Persistencia y destinos del Core

**Objetivo:** persistir únicamente la salida de expediente definida en la fase anterior, permitiendo elegir local o Google Drive como destino de cada ejecución y conservando los runs internos solo durante la ejecución o el diagnóstico autorizado.

**Tareas**

- [ ] Definir la unidad persistida como expediente (`exp-XX`) y sus dos etapas (`analisis-inicial`, `analisis-detallado`), con `context.md` como índice vigente.
- [ ] Mantener el modelo de un destino por ejecución: `JobRequest` seguirá seleccionando local o Google Drive. La CLI/Harness deberá permitir elegir ese destino sin obligar a publicar en ambos.
- [ ] Separar dos catálogos: `salida de expediente` (solo los archivos del árbol público) y `run interno` (diagnósticos y temporales no destinados al usuario). El segundo no se publica ni se conserva por defecto.
- [ ] Definir un manifiesto de persistencia versionado con `job_id`, tipo de pipeline, versión del Core/recursos, identificador de expediente, run, hashes, rutas relativas, MIME, origen y estado de validación.
- [ ] Hacer que el Core produzca la misma estructura lógica y los mismos hashes tanto si el destino es local como si es Drive, aunque sus URIs y mecanismos atómicos sean diferentes.
- [ ] Migrar la publicación actual al árbol versionado: assessment deja `analisis-<timestamp>/analisis-inicial/ficha_oportunidad.pdf` y `context.md`; detailed-analysis deja `analisis-<timestamp>/analisis-detallado/*` y `context.md`.
- [ ] Eliminar al terminar cada ejecución el input materializado, `agent-workspace`, logs, respuestas crudas de Codex, métricas, validaciones auxiliares y temporales; conservarlos solo mediante un modo diagnóstico explícito.
- [ ] Definir regeneración como nueva ejecución versionada: una carpeta `analisis-<timestamp>` nunca se modifica silenciosamente.
- [ ] Añadir pruebas con fakes de Drive y filesystem que comparen catálogos, hashes, manifests, reintentos y fallos parciales; no usar Drive real.

**Aceptación:** una ejecución publica el mismo árbol lógico en el destino elegido, local o Drive; assessment y detailed-analysis publican únicamente sus salidas contractuales; los runs internos se eliminan al terminar cuando no hay retención diagnóstica; una publicación parcial no se presenta como completada.

**Decisión pendiente de esta tarea:** confirmar si el árbol público del expediente se publica dentro de la carpeta de entrega actual, como sidecar hermano o como una carpeta/versionado separado. Esta decisión debe tomarse antes de implementar el workspace.

### Fase 3B — Mejora guiada de artefactos oficiales

**Objetivo:** mejorar el contenido y la utilidad de los artefactos visibles para negocio sin mezclar sus responsabilidades ni alterar el contrato de salida del expediente.

Los criterios concretos de contenido se incorporarán a partir de los tips que facilite el responsable de negocio. No se deben inferir ni convertir en lógica LLM hasta que estén revisados.

**Tareas comunes**

- [ ] Recopilar y validar los tips de negocio para cada artefacto, separando requisitos obligatorios, recomendaciones editoriales y ejemplos.
- [ ] Convertir los tips aprobados en reglas, checklist o instrucciones versionadas dentro de `resources/`, según sean deterministas o de contenido asistido.
- [ ] Definir para cada artefacto su audiencia, objetivo, entradas, límites y relación con evidencias.
- [ ] Añadir validaciones y tests de contrato que comprueben presencia, trazabilidad y formato, sin exigir textos LLM byte a byte.
- [ ] Registrar versión del artefacto y de sus criterios en los metadatos del resultado.

**Tarea 3B.1 — Mejorar `resumen_tecnico.docx`**

- [ ] Recibir los tips específicos para mejorar el resumen técnico.
- [ ] Revisar estructura, orden, nivel de detalle, claridad para técnico/arquitecto/revisor y cobertura de requisitos.
- [ ] Incorporar los tips aprobados en la plantilla, el generador o las reglas correspondientes.
- [ ] Verificar que cada afirmación relevante conserva referencias trazables al dossier/evidencias.
- [ ] Añadir fixtures y pruebas de renderizado y contenido.

**Tarea 3B.2 — Mejorar `guia_preparacion_oferta.docx`**

- [ ] Recibir los tips específicos para mejorar la guía de preparación de oferta.
- [ ] Revisar que distingue acciones, responsables, entregables, riesgos, pendientes y decisiones necesarias.
- [ ] Incorporar los tips aprobados en la plantilla, el generador o las reglas correspondientes.
- [ ] Evitar que la guía convierta recomendaciones o pendientes en requisitos contractuales no demostrados.
- [ ] Añadir fixtures y pruebas de contenido, pendientes y trazabilidad.

**Tarea 3B.3 — Mejorar `ficha_oportunidad.pdf`**

- [ ] Recibir los tips específicos para mejorar la ficha de oportunidad.
- [ ] Revisar que sirve como salida ejecutiva del `assessment`, sin presentar como confirmado lo que aún no esté validado.
- [ ] Incorporar los tips aprobados en el modelo, plantilla HTML/PDF o reglas correspondientes.
- [ ] Mantener la ficha autocontenida y trazable a la extracción, decisión y evidencias del análisis inicial.
- [ ] Añadir pruebas de contenido, generación PDF, límites de páginas y datos incompletos.

**Aceptación:** cada artefacto tiene una responsabilidad diferenciada, criterios aprobados y versionados, salida reproducible, trazabilidad a sus fuentes y tests específicos. Ninguna mejora de un artefacto cambia silenciosamente el contenido o contrato de los otros.

### Fase 4 — Primer LitMan Harness: Codex como interfaz

**Objetivo:** un usuario no técnico puede abrir Codex App y gestionar una licitación por lenguaje natural.

**Tareas**

- [ ] Crear plantilla de workspace de negocio con `AGENTS.md` propio; impedir que herede por accidente las skills e instrucciones del repositorio de desarrollo.
- [ ] Incluir **solo dos skills oficiales de ejemplo** al inicio:
  - `litman-listar-licitaciones`: consultar el inventario de expedientes autorizado en Drive.
  - `litman-analizar-licitacion`: seleccionar expediente, comprobar estado y lanzar pipeline del Core.
- [ ] Crear comandos Python deterministas que las skills invocarán (por ejemplo, `litman tenders list`, `litman analyze ...`).
- [ ] Preparar un flujo posterior de refinamiento de borradores desde Codex App, primero con instrucciones generales y edición supervisada; solo convertirlo en skill cuando haya un procedimiento estable.
- [ ] Investigar y probar explícitamente la **ejecución anidada**: Codex App ordena un análisis cuyo Core invoca Codex CLI. Verificar autenticación, concurrencia, permisos, logs y costos.
- [ ] Añadir checks de prerequisitos: compatibilidad real de Codex App con el sistema operativo objetivo, Python/uv, Codex CLI, herramientas de renderizado y conectividad autorizada.
- [ ] Documentar cómo se inicia y cómo se reanuda un trabajo de una sesión a otra.

**Aceptación:** desde Codex App se puede pedir «lista las licitaciones» y «analiza esta», invocando el Core sin construir un chatbot propio.

#### Skills oficiales, personales y contribuciones

- **Oficiales:** vienen del repo y se actualizan con las releases. Mantener nombres reservados, por ejemplo `litman-*`.
- **Personales:** cada usuario puede añadir carpetas `SKILL.md` propias al workspace, fuera del conjunto gestionado por el instalador.
- **Actualización:** el actualizador solo modifica elementos oficiales identificados en un manifest; **no sobrescribe** las skills personales ni las oficiales editadas localmente sin aviso/backup.
- **Volver al repositorio:** si una skill personal resulta útil para todos, se comparte voluntariamente por PR/revisión y puede promocionarse a oficial. No se sube al GitHub central automáticamente.
- **Seguridad:** el `AGENTS.md` y las skills orientan a Codex, pero no sustituyen los permisos del sistema ni un sandbox.

### Fase 5 — Workspace por licitación y sincronización Drive multiusuario

**Objetivo:** descargar, modificar y compartir expedientes con seguridad, incluso si varias personas trabajan a la vez.

**Tareas**

- [ ] Definir un vínculo estable entre **expediente** (identidad de negocio), **run** (ejecución inmutable) y **workspace** (copia editable del usuario).
- [ ] Reutilizar el adaptador de Drive actual y crear comandos de workspace: abrir, estado, pull, push.
- [ ] Definir una clasificación mínima de archivos: **fuentes** y **análisis oficiales** (solo lectura), **borradores de trabajo** (editables), **entregables aprobados** (publicación controlada), **metadatos de sincronización** (locales).
- [ ] Mantener por archivo: `drive_file_id`, ubicación, MIME, revisión/versión remota disponible, hash local, estado sincronizado y asociación al expediente.
- [ ] Implementar descarga incremental y `sync status`; `changes.list` puede ayudar a seguir modificaciones, con tratamiento especial de shared drives y permisos.
- [ ] Implementar `sync pull` sin sobrescribir modificaciones locales no publicadas.
- [ ] Implementar `sync push` **explícito y supervisado**: previsualizar archivos, destino y acción; no subir secretos ni metadatos privados.
- [ ] Para una **V1 segura**, publicar borradores conflictivos como **nuevas versiones/archivos únicos**, nunca sobrescribir el mismo fichero compartido por defecto.
- [ ] Gestionar dos cambios simultáneos: preservar ambas copias, avisar y exigir resolución antes de declarar una versión como vigente.
- [ ] Si en el futuro es imprescindible actualizar *in place* un fichero o un índice «versión actual», añadir coordinación de escrituras **servidor-side** (p. ej., mediante la API/BD central) o una garantía atómica verificada; consultar el `version` de Drive justo antes del upload **no basta** para evitar carreras.
- [ ] Definir tratamiento de borrados, renombres, carpetas movidas, pérdidas de permisos, reintentos, duplicados, cortes de red y operaciones parcialmente completadas.
- [ ] Crear fixtures/fakes de Drive y pruebas de concurrencia simulada con dos workspaces independientes.

**Aceptación:** dos usuarios modifican archivos distintos y sincronizan correctamente; si modifican el mismo archivo, se preservan ambas variantes, se notifica conflicto y nadie pierde trabajo. Los comandos son idempotentes frente a reintentos.

La estructura del workspace está definida en el apartado 4.3. La fase 5 añade sobre ella el estado de sincronización y las reglas de concurrencia; no crea un segundo árbol de expedientes.

### Fase 6 — Refinamiento interactivo y trazabilidad de propuestas

**Objetivo:** Codex App deja de ser solo un lanzador de análisis y ayuda a preparar ofertas.

**Tareas**

- [ ] Establecer límites claros: Codex puede **proponer y editar borradores** del workspace, nunca fuentes originales ni evidencias verificadas.
- [ ] Definir herramientas de lectura/consulta de dossier, referencias, análisis y documentos generados.
- [ ] Permitir revisiones iterativas de apartados, adjuntos y propuestas; conservar versiones y resúmenes de cambios.
- [ ] Actualizar `PROGRESS.md` o registro equivalente con decisiones de trabajo y pendientes sin reescribir el análisis oficial.
- [ ] Separar borrador, revisión humana y versión aprobada antes de publicarla como entregable.
- [ ] Añadir una skill de refinamiento **solo** si el uso real demuestra que se repite el procedimiento.

**Aceptación:** una persona puede revisar y mejorar una propuesta en sesiones sucesivas, recuperar contexto y subir resultados revisados sin alterar las fuentes ni presentar cambios del agente como evidencia validada.

### Fase 7 — Instaladores, actualizaciones y CI/CD

**Objetivo:** distribuir, probar y actualizar LitMan Core, la imagen Docker y LitMan Harness sin que el usuario tenga que clonar el repositorio.

**Tareas**

- [ ] `setup-dev.sh`: desarrollo local del repositorio completo.
- [ ] `build-docker.sh`: construcción y validación de imagen.
- [ ] `build-harness.sh`: paquete Core + instrucciones, skills y plantilla de workspace; incluir instalador usable por el usuario.
- [ ] `check-harness.sh`: validar dependencias, versiones, autenticación y acceso a Drive sin imprimir secretos.
- [ ] GitHub Actions (o CI corporativa): tests, build de wheel, imagen Docker, bundle Harness, smoke tests y publicación de versiones.
- [ ] Publicar el bundle Harness en un canal autorizado y la imagen Docker solo donde sea necesaria para la distribución actual.
- [ ] Diseñar `litman update`/actualizador equivalente: actualización versionada, manifest de ficheros oficiales, migraciones compatibles y **preservación de workspaces y skills personales**.
- [ ] Añadir mecanismo de rollback; fijar compatibilidad `versión Core ↔ versión recursos ↔ versión harness`.
- [ ] Probar instalación limpia y actualización desde versión anterior en los sistemas operativos objetivo.

**Aceptación:** una release genera distribución Docker y LitMan Harness de la misma versión; un usuario instala/actualiza sin clonar Git, mantiene expedientes y personalizaciones y puede comprobar el estado de su instalación.

## 6. Orden de ejecución recomendado

| Orden | Fase | Dependencia principal | Hito |
| --- | --- | --- | --- |
| 0 | Contratos y baseline | — | Punto de partida protegido |
| 1 | Core Python autónomo | 0 | Corre sin Docker |
| 2A | Contrato de runtime | 1 | Entorno verificable para Core |
| 2B | Distribución Docker | 2A | Imagen aislada del Core |
| 2C | Distribución LitMan Harness | 2A | Uso local desde Codex App |
| 3 | Salida de expediente y contexto | 1 | Árbol público y context.md |
| 3A | Persistencia y destinos | 1 y 3 | Árbol de expediente local o Drive |
| 3B | Mejora guiada de artefactos | 3 y tips aprobados | Artefactos oficiales mejorados |
| 4 | Primer LitMan Harness | 2C, 3A y 3B | Listar y analizar desde Codex App |
| 5 | Workspace + sync segura | 4 | Trabajo multiusuario sin pérdida |
| 6 | Refinamiento interactivo | 5 | Preparación real de ofertas |
| 7 | CI/CD y actualizaciones completas | 2B, 2C, 3A, 3B y 4 | Distribución mantenible |

**Paralelización:** las distribuciones Docker y Harness pueden avanzar en paralelo después de fijar el contrato de runtime (2A). La sincronización (fase 5) requiere diseño y pruebas propias antes de habilitar pushes compartidos.

## 7. Decisiones fijadas, pendientes y fuera de alcance

### Fijadas

1. **Un repo y un Core Python.** El runtime del Core no conoce Docker.
2. **Dos formas de ejecución:** Docker para ejecución aislada y LitMan Harness para uso local con Codex App.
3. **Codex App es la interfaz conversacional local;** no se construye chatbot propio.
4. **Skills oficiales de ejemplo, extensibilidad personal y aportaciones opcionales al repo.**
5. **`context.md` derivado de resultados validados y `PROGRESS.md` separado.**
6. **Drive compartido, workspace individual, sincronización explícita y política no destructiva.**
7. **Destinos equivalentes:** cada análisis validado puede conservarse con el mismo contrato y estructura en local o en Drive, eligiendo un destino por ejecución.
8. **Autenticación Drive:** se mantiene el mecanismo actual de cuenta de servicio configurada por usuario mediante `GOOGLE_APPLICATION_CREDENTIALS`; las credenciales no se incluyen en las distribuciones.

### Por resolver antes de implementar los módulos afectados

- Plan concreto de compatibilidad y retirada de `litman-analysis` y `litman-analysis-worker` durante la transición a `litman-core`.
- Plataformas de negocio admitidas (Ubuntu, Windows, macOS) y disponibilidad/comportamiento real de Codex App y de herramientas auxiliares en cada una.
- Permisos mínimos de la cuenta de servicio configurada por usuario y tratamiento de Shared Drives.
- Contrato de publicación del árbol del expediente y estrategia de transición desde los entregables oficiales actuales.
- Qué documentos se editan localmente (Markdown, DOCX, etc.) y cómo se revisan/aprueban.
- Decisión del destino y forma de publicación del árbol del expediente (dentro de la carpeta actual, sidecar hermano o carpeta/versionado separado).
- Empaquetado y actualización de dependencias externas a Python, incluido Codex CLI.
- Política de retención local y en Drive para runs, salidas de expediente, diagnósticos y borradores.
- Necesidad futura de una API de coordinación para versionado compartido cuando se quiera un «documento vigente» único.

### Fuera de alcance inicial

- Editor colaborativo en tiempo real para DOCX.
- Nuevo orquestador de pipelines o refactor completo de `src/litman_core/` más allá de la migración de namespace aprobada.
- Migración obligatoria de la integración Codex CLI a otro SDK.
- Sincronización automática permanente con Drive.
- Publicación de skills personales al repositorio sin revisión.

## 8. Flujo esperado de usuario

1. Una licitación y sus documentos están disponibles en Drive o en una entrada local autorizada.
2. El Core ejecuta `assessment` o `detailed-analysis`, valida el run y guarda el árbol de salida correspondiente en el destino elegido: local o Drive.
3. El responsable abre Codex App en su instalación con LitMan Harness y pregunta: «¿Qué licitaciones tenemos?».
4. Codex ejecuta la skill de listado; elige un expediente y prepara su workspace con un pull seguro.
5. Pide «haz análisis detallado»: la skill llama al Core Python local, que ejecuta su pipeline (incluyendo el Codex CLI interno).
6. El Core produce o actualiza `context.md`; detailed-analysis añade el dossier y los documentos en `analisis-detallado/`; el usuario revisa resultados.
7. El usuario pide refinamientos; Codex modifica **borradores**, mantiene progreso y presenta cambios para revisión.
8. El usuario solicita publicar; `sync status` y `sync push` muestran cambios y preservan versiones conflictivas.
9. Otro usuario puede continuar desde su workspace sin sobrescrituras silenciosas.

## 9. Reglas de ejecución de cada fase

- Usar la skill de desarrollo `research-design` antes de una implementación; `implement` solo con `design.md` aprobado.
- Un alcance por fase o subfase, cambios mínimos y contratos explícitos.
- Priorizar tests deterministas con fixtures y fakes; llamadas reales a Drive solo con autorización.
- Ejecutar las comprobaciones actuales cuando correspondan:

```bash
UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q
docker compose config --quiet
docker compose build
```

- Añadir además pruebas de instalación de wheel, smoke tests local/Docker, sincronización con dos usuarios y actualizaciones del harness en las fases indicadas.
- Actualizar `docs/architecture.md`, `docs/codebase-map.md` y `docs/decisions.md` **solo cuando la implementación altere de verdad esas descripciones**; mantener este documento como diseño objetivo hasta entonces.

## 10. Fuentes técnicas consultadas

Estas referencias respaldan decisiones de empaquetado y seguimiento de cambios; no sustituyen la verificación del código del repositorio:

- uv — [Building and publishing a package](https://docs.astral.sh/uv/guides/publish/) y [CLI de uv](https://docs.astral.sh/uv/reference/cli/).
- Google Drive API — [Retrieve changes](https://developers.google.com/workspace/drive/api/guides/manage-changes), [Files resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/files) y [files.update](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/update).
- OpenAI — [Guía de skills](https://developers.openai.com/plugins/build/skills).

---

**Resumen de la decisión arquitectónica:** **LitMan Core es un paquete Python único**. Se instala de forma **local** junto con LitMan Harness, o se empaqueta en **Docker** para conservar la ejecución aislada. Cada análisis validado produce el árbol de salida de su etapa y un `context.md` vigente, persistibles con el mismo contrato en el destino elegido —local o Drive—; el trabajo multiusuario se protege con versiones y sincronización no destructiva.
