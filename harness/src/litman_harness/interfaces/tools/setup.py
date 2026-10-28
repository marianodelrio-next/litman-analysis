"""Local setup: choose the Core provider (and optional model) once per machine."""
from __future__ import annotations

import os

from . import Tool, schema
from ...adapters.core import PROVIDERS
from ...settings import setup as _setup

TOOLS = (
    Tool("setup", "Mutación local: configura o cambia el proveedor y el modelo de análisis de LitMan Core "
                  "para esta instalación, tras comprobar `litman-core info`. Requiere proveedor; consulta "
                  "`diagnose` para conservar el actual. Si se omite el modelo, usa el predeterminado de Core. "
                  "Los planes de análisis ya preparados conservan su configuración. No valida la disponibilidad "
                  "del modelo, no toca Drive ni requiere un plan previo.",
         schema({"provider": {"type": "string", "enum": sorted(PROVIDERS)},
                 "model": {"type": "string"}},
                ("provider",)),
         lambda ctx, args: _setup(os.environ, args["provider"], args.get("model")),
         mutates=True),
)
