# Tarea 4 — Completar producto y releases

> Estado: roadmap pendiente; debe dividirse antes de implementar.

## Objetivo

Mejorar los entregables con criterios de negocio aprobados, permitir su
refinamiento trazable y establecer releases y actualizaciones seguras.

## Líneas de trabajo

- Recoger criterios por artefacto y convertirlos en reglas, plantillas o
  instrucciones versionadas según corresponda.
- Refinar únicamente documentos derivados, conservando fuentes, análisis base,
  autoría, versiones y aprobación humana.
- Separar el progreso del usuario del contexto oficial generado por Core.
- Crear instaladores y actualizadores idempotentes que preserven expedientes y
  skills personales.
- Añadir CI para tests, wheel, imagen, Harness, compatibilidad y release.
- Documentar rollback y matriz de versiones soportadas.

## Criterios de aceptación

- Cada cambio mantiene trazabilidad hasta evidencias y versión.
- Las actualizaciones no borran datos ni personalizaciones.
- Los artefactos publicados proceden de builds reproducibles y verificados.
- Un release fallido puede revertirse sin corromper el workspace.

## Dependencias y división

Requiere las tareas 1–3. Antes de implementarla debe dividirse en tareas
independientes por artefacto, refinamiento, instalador y CI/CD.

