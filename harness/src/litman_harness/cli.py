from __future__ import annotations

import argparse
import json
import sys
import os
from pathlib import Path
from typing import Any

from .configured import MetadataGateway
from .models import HarnessError
from .service import ExpedienteService


def emit(payload: dict[str, Any], *, error: bool = False) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr if error else sys.stdout)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="litman", description="Adaptador local JSON para expedientes LitMan")
    parser.add_argument("command", choices=("login", "identity", "inspect", "status", "preview-incorporation", "apply-incorporation", "recover"))
    parser.add_argument("--json", required=True, help="Solicitud JSON; nunca incluya tokens ni secretos")
    args = parser.parse_args(argv)
    try:
        request = json.loads(args.json)
        config = os.environ.get("LITMAN_HARNESS_METADATA")
        if not config: raise HarnessError("adapter_not_configured", "Configure OAuth personal o LITMAN_HARNESS_METADATA; esta CLI no acepta tokens ni claves")
        service = ExpedienteService(MetadataGateway(Path(config)))
        if args.command == "identity": payload = service.identity()
        elif args.command in {"inspect", "status"}: payload = service.inspect(str(request["folder_id"]))
        else: raise HarnessError("read_only_adapter", "Esta configuración determinista solo permite operaciones de lectura")
        emit({"ok": True, "result": payload})
    except HarnessError as exc:
        emit({"ok": False, "error": {"code": exc.code, "message": str(exc), "details": exc.details}}, error=True)
        raise SystemExit(2)
    except (TypeError, json.JSONDecodeError) as exc:
        emit({"ok": False, "error": {"code": "invalid_request", "message": str(exc)}}, error=True)
        raise SystemExit(2)
