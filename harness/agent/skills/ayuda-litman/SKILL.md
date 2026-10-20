---
name: ayuda-litman
description: Explica qué puede hacer LitMan cuando la persona pregunta "qué puedes hacer", pide "ayuda" o "qué herramientas tienes", con una frase de ejemplo para cada cosa.
---

Responde en lenguaje de negocio, agrupando por lo que la persona quiere
conseguir. No hace falta nombrar las herramientas salvo que lo pida; usa los
ejemplos para que vea cómo pedirlo. Todo cambio en Drive se prepara primero
como vista previa y sólo se aplica cuando la persona lo acepta.

## Preparar el equipo

- `diagnose`: comprueba que LitMan, la cuenta de Google, el motor de análisis
  y las API de Google Docs y Google Sheets están listos.
  Ejemplo: "prepara mi equipo" o "¿funciona todo bien?"
- `setup`: elige qué proveedor (y modelo) usa el análisis de LitMan.
  Ejemplo: "usa Codex para los análisis"
- `identity`: dice con qué cuenta de Google trabaja LitMan.
  Ejemplo: "¿con qué cuenta estás conectado?"

## Conectar y organizar la licitación

- `inspect`: hace inventario de la carpeta de la licitación y propone qué
  hacer.
  Ejemplo: "mira qué hay en la carpeta de la licitación"
- `status`: dice en qué punto está la licitación y cuál es el siguiente paso.
  Ejemplo: "conecta la licitación con ID ..." o "¿cómo va esta licitación?"
- `preview_incorporation`: prepara lo que falta para que LitMan gestione la
  licitación (carpetas, originales, oferta, fase y contexto).
  Ejemplo: "organiza la licitación para trabajar con LitMan"
- `apply_incorporation`: aplica esa organización cuando la aceptas.
  Ejemplo: "sí, aplica la organización"
- `recover`: muestra en qué quedó una operación interrumpida.
  Ejemplo: "¿en qué quedó el análisis que se cortó?"

## Análisis

- `preview_analysis`: prepara el análisis de los pliegos con los originales y
  el tipo de análisis elegidos.
  Ejemplo: "analiza los pliegos de esta licitación"
- `execute_analysis`: ejecuta el análisis aceptado y publica sus resultados en
  Drive.
  Ejemplo: "adelante con el análisis"
- `discard_analysis`: descarta un análisis local que no se publicó; no toca
  Drive.
  Ejemplo: "descarta el análisis que no se publicó"
- `preview_publication`: prepara la publicación de un análisis que quedó sin
  publicar.
  Ejemplo: "publica el análisis que quedó pendiente"
- `apply_publication`: publica ese análisis cuando lo aceptas.
  Ejemplo: "sí, publícalo"

## Resumen de la licitación

- `preview_summary`: prepara el resumen de contexto de la licitación, con la
  fuente de cada dato.
  Ejemplo: "resume la licitación"
- `apply_summary`: guarda el resumen aceptado en `contexto.md`.
  Ejemplo: "guarda el resumen"

## Ver y leer archivos

- `list_folder`: lista lo que hay en la carpeta de la licitación o en una
  subcarpeta.
  Ejemplo: "¿qué hay en la carpeta Oferta?"
- `search_in_dossier`: busca archivos por nombre en toda la licitación.
  Ejemplo: "busca el archivo del presupuesto"
- `get_file_info`: da los detalles de un archivo y qué puedes hacer con él
  (editar, renombrar, mover, comentar).
  Ejemplo: "¿puedo editar el archivo de solvencia?"
- `read_file`: lee cualquier archivo de la licitación: PDF, Word, texto,
  Markdown, CSV, Excel, Google Docs, Hojas de cálculo o Presentaciones.
  Ejemplo: "lee el Excel de costes" o "¿qué pone en la presentación?"
- `list_comments`: muestra los comentarios de un archivo y sus respuestas.
  Ejemplo: "¿qué comentarios hay en la memoria técnica?"

## Leer documentos

- `read_document`: lee los pliegos originales y los resultados del análisis
  (PDF o DOCX).
  Ejemplo: "¿qué dice el pliego técnico sobre la solvencia?"
- `read_google_doc`: lee un Google Doc de la licitación, por ejemplo la
  propuesta técnica.
  Ejemplo: "lee la propuesta técnica de la carpeta Oferta"

## Documentos de Google Docs

- `preview_document_edit`: prepara cambios de texto en un Google Doc
  (sustituir, insertar después de un párrafo o añadir al final).
  Ejemplo: "cambia el plazo de entrega a 30 días en la propuesta"
- `apply_document_edit`: aplica esos cambios cuando los aceptas.
  Ejemplo: "sí, aplica los cambios"
- `preview_document_creation`: prepara un Google Doc nuevo a partir de un
  texto o de un DOCX de la licitación.
  Ejemplo: "crea un Google Doc con la memoria a partir del DOCX"
- `apply_document_creation`: crea ese documento cuando lo aceptas.
  Ejemplo: "sí, créalo"

## Hojas de cálculo

- `preview_sheet_edit`: prepara cambios en un Google Sheet de la licitación
  (actualizar un rango o añadir filas al final).
  Ejemplo: "pon 1.500 € en la celda B2 del presupuesto" o "añade una fila con
  estos gastos al presupuesto"
- `apply_sheet_edit`: aplica esos cambios cuando los aceptas.
  Ejemplo: "sí, aplica los cambios en la hoja"

## Lo que no está en esta lista

Si la persona pide algo que no aparece aquí, dile que LitMan todavía no puede
hacerlo y sugiérele pedírselo al desarrollador de LitMan. No lo hagas por
otra vía: nunca con computer use, el navegador, otros conectores de Drive ni
scripts.
