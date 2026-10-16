"""Small, deterministic dotenv reader used by the public CLI."""
from __future__ import annotations

import os
import re
from pathlib import Path

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def load_env_file(path: Path) -> None:
    """Load literal KEY=value lines; existing environment values always win."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ValueError(f"No existe el archivo de entorno: {path}") from exc
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"Archivo de entorno inválido en {path}:{number}")
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if not _NAME.fullmatch(name):
            raise ValueError(f"Nombre de variable inválido en {path}:{number}")
        if value[:1] in {"'", '"'}:
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f"Comilla sin cerrar para {name} en {path}:{number}")
            value = value[1:-1]
        elif value.endswith(("'", '"')):
            raise ValueError(f"Comilla inválida para {name} en {path}:{number}")
        os.environ.setdefault(name, value)
