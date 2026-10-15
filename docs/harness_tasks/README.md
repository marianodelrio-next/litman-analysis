# Tareas para el harness de licitaciones

Estas tareas describen el trabajo pendiente para que personal de negocio prepare una oferta desde Codex App o Claude Code, con Google Drive como espacio compartido. No son un diseño aprobado ni autorizan todavía la implementación. El diseño que se redacte después deberá resolver las decisiones abiertas y podrá ajustar el orden o el alcance.

El punto de partida es la wheel de LitMan Core: `assessment` sirve para decidir si interesa una licitación y `detailed-analysis` se ejecuta cuando la persona decide tramitarla. Core ya genera documentos, entre ellos un DOCX de propuesta, pero no mantiene una oferta colaborativa después de publicarla. La persona trabajará con su asistente y con Drive en el navegador; no se prevé UI propia, servidor o Docker para este uso. Core no necesita generar ningún artefacto nuevo para el contexto: el harness creará un único `contexto.md` breve por licitación a partir del expediente y las salidas ya disponibles.

## Decisión editorial ya tomada

La prueba de conversión del DOCX de Core, edición mediante API, comentarios, sugerencias, formato, control de revisión y exportación a DOCX/PDF, junto con la comprobación en navegador comunicada por negocio, permiten adoptar **Google Docs nativo como documento vivo**. El DOCX se importa una sola vez como punto de partida; después se opera sobre el ID del Google Doc y ningún reanálisis reemplaza una oferta editada. El PDF de prueba conservó una presentación coherente; en cada entrega se revisarán visualmente las páginas contractualmente críticas. Los comentarios programáticos tendrán degradación explícita si la capacidad no está disponible para una cuenta. La coedición con dos cuentas y los conflictos del mismo apartado se incluyen en las pruebas de la tarea editorial, sin suponer que la API resuelve el significado de cambios simultáneos.

Orden propuesto:

1. [Adaptar Core a Codex/Claude y Windows/Ubuntu](02-core-proveedores-y-portabilidad.md). Permite ejecutar los análisis con la suscripción disponible de cada persona.
2. [Construir el expediente y las operaciones de Drive](04-expediente-drive.md). Establece identidad, estructura, contexto breve y trazabilidad sin sincronización indiscriminada.
3. [Construir la edición, la revisión y las entregas](05-edicion-y-entregas.md). Usa Google Docs nativo y depende de las operaciones de Drive.
4. [Distribuir el harness e instalarlo desde un clon](06-distribucion-y-setup.md). Integra las piezas en un recorrido sencillo para Windows y Ubuntu.

Hay dependencias cruzadas: conviene prototipar la instalación y OAuth pronto, aunque se cierre al final; y ninguna tarea debe sobrescribir una oferta que alguien ya haya editado. Las pruebas reales de Drive, Codex o Claude requieren una carpeta y cuentas de prueba autorizadas. Los secretos y documentos de licitaciones reales no forman parte de las pruebas automatizadas.
