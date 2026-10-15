# Tareas para el harness de licitaciones

Estas tareas describen el trabajo para que personal de negocio prepare una oferta desde Codex App o Claude Code, con Google Drive como espacio compartido. Cada una se concreta en un diseño aprobado antes de implementarse; el estado real del harness está en [harness-development.md](../harness-development.md).

El punto de partida es la wheel de LitMan Core: `assessment` sirve para decidir si interesa una licitación y `detailed-analysis` se ejecuta cuando la persona decide tramitarla. Core ya genera documentos, entre ellos un DOCX de propuesta, pero no mantiene una oferta colaborativa después de publicarla. La persona trabajará con su asistente y con Drive en el navegador; no se prevé UI propia, servidor o Docker para este uso. Core no necesita generar ningún artefacto nuevo para el contexto: el harness creará un único `contexto.md` breve por licitación a partir del expediente y las salidas ya disponibles.

## Decisión editorial ya tomada

La prueba de conversión del DOCX de Core, edición mediante API, comentarios, sugerencias, formato, control de revisión y exportación a DOCX/PDF, junto con la comprobación en navegador comunicada por negocio, permiten adoptar **Google Docs nativo como documento vivo**. El DOCX se importa una sola vez como punto de partida; después se opera sobre el ID del Google Doc y ningún reanálisis reemplaza una oferta editada. El PDF de prueba conservó una presentación coherente; en cada entrega se revisarán visualmente las páginas contractualmente críticas. Los comentarios programáticos tendrán degradación explícita si la capacidad no está disponible para una cuenta. La coedición con dos cuentas y los conflictos del mismo apartado se incluyen en las pruebas de la tarea editorial, sin suponer que la API resuelve el significado de cambios simultáneos.

Orden y estado:

1. **Adaptar Core a Codex/Claude (Ubuntu)** — hecho. Permite ejecutar los análisis con la suscripción disponible de cada persona.
2. **Expediente y operaciones de Drive** (antigua tarea 04) — hecho y validado en Drive real con una cuenta: identidad OAuth personal, estructura, manifiesto, `contexto.md` con resumen aceptado, análisis, publicación y oferta viva. Pendiente: prueba con segunda cuenta y registro MCP en las aplicaciones.
3. **Edición, revisión y entregas** (antigua tarea 05) — diseño pendiente de aprobación. Usa Google Docs nativo sobre la base anterior.
4. **Distribución e instalación desde un clon** (antigua tarea 06) — pendiente. Integra las piezas en un recorrido sencillo para Windows y Ubuntu, incluido el registro del MCP, las skills y los subagentes.

Hay dependencias cruzadas: conviene prototipar la instalación y OAuth pronto, aunque se cierre al final; y ninguna tarea debe sobrescribir una oferta que alguien ya haya editado. Las pruebas reales de Drive, Codex o Claude requieren una carpeta y cuentas de prueba autorizadas. Los secretos y documentos de licitaciones reales no forman parte de las pruebas automatizadas.
