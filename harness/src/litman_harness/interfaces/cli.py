"""``litman <operation> [--json '{...}']``: prints the shared operation envelope.

``litman login``, ``litman install`` and ``litman uninstall`` are CLI-only:
they are not MCP operations and never appear in ``registry()``/`tools/list``.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

from .. import installation
from ..errors import HarnessError
from .tools import error_envelope, invoke, registry


def emit(payload: dict[str, Any], *, error: bool = False) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr if error else sys.stdout)


def login() -> dict[str, Any]:
    from .assembly import oauth_provider
    try:
        return {"ok": True, "result": oauth_provider().login()}
    except HarnessError as exc:
        return error_envelope(exc.code, str(exc), exc.details)


def install(argv: list[str]) -> dict[str, Any]:
    parser = argparse.ArgumentParser(prog="litman install", description="Instala o actualiza LitMan en este equipo")
    parser.add_argument("--app", choices=sorted(installation.APPS))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--oauth-client", type=Path)
    parser.add_argument("--delete-original", action="store_true")
    args = parser.parse_args(argv)
    if bool(args.app) != bool(args.source):
        parser.error("--app y --source deben indicarse juntos")
    if not args.app and not args.oauth_client:
        parser.error("indique --app/--source o --oauth-client")
    if args.delete_original and not args.oauth_client:
        parser.error("--delete-original sólo se usa junto con --oauth-client")
    try:
        results: dict[str, Any] = {}
        if args.app:
            results["install"] = installation.install(app=args.app, source=args.source, home=Path.home(),
                                                       env=os.environ)
        if args.oauth_client:
            results["oauth_client"] = installation.import_oauth_client(
                args.oauth_client, delete_original=args.delete_original, env=os.environ)
        return {"ok": True, "result": results}
    except HarnessError as exc:
        return error_envelope(exc.code, str(exc), exc.details)


def uninstall(argv: list[str]) -> dict[str, Any]:
    parser = argparse.ArgumentParser(prog="litman uninstall", description="Desinstala LitMan de este equipo")
    parser.add_argument("--remove-workspace", action="store_true")
    parser.add_argument("--purge-data", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = installation.uninstall(home=Path.home(), env=os.environ, remove_workspace=args.remove_workspace,
                                         purge_data=args.purge_data)
        if result["failed"]:
            return error_envelope(
                "uninstall_incomplete",
                "No se pudieron eliminar algunos elementos. Cierre los programas que puedan estar "
                "usando esos archivos o carpetas y vuelva a ejecutar la desinstalación.",
                result,
            )
        return {"ok": True, "result": result}
    except HarnessError as exc:
        return error_envelope(exc.code, str(exc), exc.details)


def main(argv: list[str] | None = None) -> None:
    operations = {name.replace("_", "-"): name for name in registry()}
    argv = argv if argv is not None else sys.argv[1:]
    if argv[:1] == ["login"]:
        envelope = login()
        emit(envelope, error=not envelope["ok"])
        if not envelope["ok"]:
            raise SystemExit(2)
        return
    if argv[:1] == ["install"]:
        envelope = install(argv[1:])
        emit(envelope, error=not envelope["ok"])
        if not envelope["ok"]:
            raise SystemExit(2)
        return
    if argv[:1] == ["uninstall"]:
        envelope = uninstall(argv[1:])
        emit(envelope, error=not envelope["ok"])
        if not envelope["ok"]:
            raise SystemExit(2)
        return
    parser = argparse.ArgumentParser(
        prog="litman", description="Adaptador local JSON para expedientes LitMan "
        "(además: `litman login`, `litman install`, `litman uninstall`, sólo CLI)")
    parser.add_argument("operation", choices=sorted(operations))
    parser.add_argument("--json", default="{}", help="Argumentos JSON; nunca incluya tokens ni secretos")
    args = parser.parse_args(argv)
    try:
        request = json.loads(args.json)
    except json.JSONDecodeError as exc:
        envelope = error_envelope("invalid_request", f"JSON inválido: {exc.msg}")
    else:
        envelope = invoke(operations[args.operation], request)
    emit(envelope, error=not envelope["ok"])
    if not envelope["ok"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
