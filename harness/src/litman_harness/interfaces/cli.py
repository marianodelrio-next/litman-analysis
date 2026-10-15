"""``litman <operation> [--json '{...}']``: prints the shared operation envelope.

``litman login`` is CLI-only and interactive: it opens the desktop OAuth flow.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

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


def main(argv: list[str] | None = None) -> None:
    operations = {name.replace("_", "-"): name for name in registry()}
    if (argv if argv is not None else sys.argv[1:])[:1] == ["login"]:
        envelope = login()
        emit(envelope, error=not envelope["ok"])
        if not envelope["ok"]:
            raise SystemExit(2)
        return
    parser = argparse.ArgumentParser(
        prog="litman", description="Adaptador local JSON para expedientes LitMan (además: `litman login`, sólo CLI)")
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
