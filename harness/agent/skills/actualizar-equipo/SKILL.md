---
name: actualizar-equipo
description: Actualiza LitMan cuando la persona diga "actualiza mi equipo", "actualiza LitMan" o "hay una versión nueva".
---

Úsala sólo para actualizar LitMan en este equipo. No la uses para actualizar
el resumen de una licitación.

1. Ejecuta `litman check-update` y lee el resultado JSON.
   - Si `update_available` es `false`, di que LitMan ya está actualizado y
     termina.
   - Si aparece `update_source_missing`, pide que pegue una vez el comando de
     instalación de la app del [README de instalación](../../../deployment/README.md).
     Después de instalar, debe cerrar y volver a abrir la aplicación.
   - Si aparece `update_check_failed`, explica en una frase que no se pudo
     comprobar la nueva versión (por ejemplo, por falta de conexión) y sugiere
     volver a intentarlo o contactar al desarrollador.
2. Si hay una actualización, resume `changes` en español no técnico, en unas
   pocas frases. No menciones nombres de archivos ni detalles técnicos.
3. En Linux, ejecuta el valor de `command`. Si falla, explícalo en una frase y
   sugiere volver a intentarlo o contactar al desarrollador.
4. En Windows, no ejecutes `command`: pide que cierre la aplicación, pegue ese
   valor en PowerShell y vuelva a abrir la aplicación cuando termine.

Cierra y vuelve a abrir la aplicación.
