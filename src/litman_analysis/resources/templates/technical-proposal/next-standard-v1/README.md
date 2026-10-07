# Next standard v1

Plantilla runtime derivada del máster corporativo externo. Conserva la portada,
el índice, los estilos, encabezados y pies del documento de referencia, pero no
su contenido corporativo ni los ejemplos de ofertas anteriores.

El cuerpo dinámico se inserta en `[[DOCUMENT_BODY]]`. El índice se marca para
actualizarse cuando se abre el resultado en una aplicación compatible y conserva
como resultado inicial las secciones conocidas del plan.

Los textos variables de portada e índice usan los marcadores `[[COVER_LABEL]]`,
`[[COVER_TITLE]]`, `[[INDEX_TITLE]]` y `[[INDEX_ENTRIES]]`. El renderizador los
localiza en español o inglés sin duplicar la plantilla visual.

El perfil `skeleton-v1` puede insertar bloques `subheading`; se renderizan con
los estilos `Heading 2` a `Heading 6` heredados del documento máster y se añaden
como niveles secundarios al índice.

Los encabezados reutilizan la lista multinivel `numId=2` del máster. El
renderizador aplica también fuente, tamaño, color y sangría como propiedades
directas para conservar su aspecto al importar el DOCX en Google Docs. Las
restricciones tipográficas extraídas del pliego siguen teniendo prioridad.
