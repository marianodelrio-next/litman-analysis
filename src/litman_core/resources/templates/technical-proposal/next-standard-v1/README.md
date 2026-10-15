# Next standard v1

Plantilla runtime derivada del máster corporativo externo. Conserva la portada,
el índice, los estilos, encabezados y pies del documento de referencia, pero no
su contenido corporativo ni los ejemplos de ofertas anteriores.

El cuerpo dinámico se inserta en `[[DOCUMENT_BODY]]`. El índice se marca para
actualizarse cuando se abre el resultado en una aplicación compatible y conserva
como resultado inicial las secciones conocidas del plan.
Las entradas, subentradas y números de página usan Roboto Light 11, negro y sin
negrita ni cursiva. Cada entrada mantiene hipervínculo y campo `PAGEREF`; Word
actualiza la paginación al abrir el documento. Otros editores deben soportar la
actualización de campos DOCX para recalcularla automáticamente.

Los textos variables de portada e índice usan los marcadores `[[COVER_LABEL]]`,
`[[COVER_TITLE]]`, `[[INDEX_TITLE]]` y `[[INDEX_ENTRIES]]`. El renderizador los
localiza en español o inglés sin duplicar la plantilla visual.

El perfil `skeleton-v1` fija subapartados trazables del pliego o propuestos en
el plan; se renderizan con
los estilos `Heading 2` a `Heading 6` heredados del documento máster y se añaden
como niveles secundarios al índice.

Los encabezados reutilizan la lista multinivel `numId=2` del máster. El
renderizador aplica también fuente, tamaño, color y sangría como propiedades
directas para conservar su aspecto al importar el DOCX en Google Docs. Las
restricciones tipográficas extraídas del pliego siguen teniendo prioridad.

La identidad de licitación (tipo documental, título oficial, expediente,
título completo y título corto de archivo) se conserva en `document_plan.json`.
La guía editorial estructurada se conserva en `content.json` y puede excluirse
con `include_editorial_guidance = false` en la configuración de generación. Las puntuaciones confirmadas forman parte del título visible en el
índice y en el cuerpo; el título canónico permanece intacto para validar el
plan.

Los subapartados con origen `tender` reproducen el pliego; los de origen
`proposed` se eligen de forma determinista por familia semántica y nunca los
inventa el renderizador. La puntuación procede primero de la sección del
pliego y, sólo ante una relación inequívoca, de uno o varios criterios.

El nombre de salida conserva espacios, expediente, siglas y términos
significativos del título, con saneamiento y límite portable.
