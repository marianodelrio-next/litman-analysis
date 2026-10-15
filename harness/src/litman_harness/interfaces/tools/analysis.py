"""Core analysis operations (analysis and its publication under one acceptance)."""
from __future__ import annotations

from . import Tool, schema
from ...adapters.core import JOB_TYPES, PROVIDERS

TOOLS = (
    Tool("preview_analysis", "Consulta (no escribe en Drive): guarda localmente un plan que ejecuta Core con "
                             "originales, tipo y proveedor fijados y publica sus resultados (carpeta destino, "
                             "conversión de la oferta viva si procede y avance de fase). Valida antes de ejecutar.",
         schema({"folder_id": {"type": "string", "description": "ID de la carpeta de la licitación."},
                 "original_ids": {"type": "array", "items": {"type": "string"}},
                 "job_type": {"type": "string", "enum": sorted(JOB_TYPES)},
                 "provider": {"type": "string", "enum": sorted(PROVIDERS)}},
                ("folder_id", "original_ids", "job_type", "provider")),
         lambda ctx, args: ctx.services().analysis.preview(
             args["folder_id"], args["original_ids"], args["job_type"], args["provider"]).json()),
    Tool("execute_analysis", "Mutación: para el plan_id aceptado descarga los originales, ejecuta Core (minutos) "
                             "y publica en Drive sin otra aceptación. Si la publicación falla, repetir con el mismo "
                             "plan_id la reanuda sin volver a ejecutar Core. Devuelve recommended_action.",
         schema({"plan_id": {"type": "string"}}, ("plan_id",)),
         lambda ctx, args: ctx.services().analysis.execute(args["plan_id"]),
         mutates=True),
    Tool("discard_analysis", "Mutación local: borra sólo el workspace local de un análisis no publicado tras "
                             "aceptar su operation_id; no toca Drive.",
         schema({"operation_id": {"type": "string"}}, ("operation_id",)),
         lambda ctx, args: ctx.services().analysis.discard(args["operation_id"]),
         mutates=True),
)
