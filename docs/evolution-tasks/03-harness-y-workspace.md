# Tarea 3 — Construir Harness y workspace

> Estado: pendiente; requiere contratos estables de runtime y salida.

## Objetivo

Permitir usar LitMan desde Codex App con el paquete `litman-core` instalado, sin
clonar el repositorio ni duplicar el motor.

## Trabajo pendiente

1. Crear el paquete Harness con instrucciones de negocio, skills oficiales,
   plantillas, instalador y manifest de compatibilidad.
2. Implementar primero las operaciones de listar licitaciones y ejecutar
   análisis mediante la CLI pública.
3. Crear un workspace por usuario, separado del repositorio de desarrollo.
4. Diseñar `pull` y `push` explícitos con Drive, detección de conflictos e
   idempotencia.
5. Excluir secretos, caches, temporales, `.codex/`, `.agent-work/`, tests y
   Docker del paquete de usuario.

## Criterios de aceptación

- Una instalación nueva crea un workspace sin borrar datos existentes.
- Las skills invocan Core y no reimplementan pipelines.
- Dos usuarios no sobrescriben cambios remotos silenciosamente.
- Core, recursos y Harness declaran versiones compatibles.

## Pruebas

Instalación limpia, ejecución mediante CLI, dos workspaces con Drive falso,
conflictos, reintentos y actualización no destructiva.

## Dependencias

Requiere las tareas 1 y 2 terminadas.

