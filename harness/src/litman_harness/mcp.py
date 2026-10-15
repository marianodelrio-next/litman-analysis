from __future__ import annotations

"""Minimal stdio JSON-RPC discovery surface.  Business calls are injected by the host in tests/setup."""
import json
import os
import sys
from pathlib import Path

from .configured import MetadataGateway
from .service import ExpedienteService

TOOLS = [
    {"name": "identity", "description": "Consulta de solo lectura: cuenta OAuth activa."},
    {"name": "inspect", "description": "Consulta de solo lectura: inspecciona un expediente por ID."},
    {"name": "status", "description": "Consulta de solo lectura: devuelve estado recuperable por IDs."},
    {"name": "preview_incorporation", "description": "No escribe: prepara un plan de incorporación concreto."},
    {"name": "apply_incorporation", "description": "Cambia Drive solo con el plan_id previamente aceptado."},
    {"name": "preview_analysis", "description": "No escribe: prepara el análisis local y su catálogo previsto."},
    {"name": "recover", "description": "Consulta recursos pendientes por operation_id; no borra nada."},
]

def main() -> None:
    for line in sys.stdin:
        try:
            message = json.loads(line)
            method = message.get("method")
            if method == "tools/list": result = {"tools": TOOLS}
            elif method == "tools/call":
                config = os.environ.get("LITMAN_HARNESS_METADATA")
                if not config: result = {"error": {"code": "adapter_not_configured", "message": "Configure OAuth personal o LITMAN_HARNESS_METADATA; no se aceptan claves ni tokens por stdio."}}
                else:
                    service = ExpedienteService(MetadataGateway(Path(config)))
                    name = message.get("params", {}).get("name"); arguments = message.get("params", {}).get("arguments", {})
                    if name == "identity": result = {"content": [{"type": "text", "text": json.dumps(service.identity(), ensure_ascii=False)}]}
                    elif name in {"inspect", "status"}: result = {"content": [{"type": "text", "text": json.dumps(service.inspect(str(arguments["folder_id"])), ensure_ascii=False)}]}
                    else: result = {"error": {"code": "read_only_adapter", "message": "La configuración de metadatos solo permite consultas."}}
            else: result = {"error": {"code": "method_not_found", "message": "Método MCP no admitido"}}
            print(json.dumps({"jsonrpc": "2.0", "id": message.get("id"), "result": result}, ensure_ascii=False), flush=True)
        except json.JSONDecodeError:
            print(json.dumps({"jsonrpc": "2.0", "error": {"code": -32700, "message": "JSON inválido"}}), flush=True)
