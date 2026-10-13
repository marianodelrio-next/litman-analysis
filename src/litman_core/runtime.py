"""Runtime directories safe for arbitrary non-root container UIDs."""
from __future__ import annotations
import os
from pathlib import Path
class RuntimeInitializationError(RuntimeError): pass
def initialize_runtime(*, home: Path, codex_home: Path, workspace: Path, runs: Path, output: Path | None = None, input_dir: Path | None = None) -> None:
    for path in (home, codex_home, workspace):
        path.mkdir(parents=True, exist_ok=True); path.chmod(0o700); _writable(path, "directorio runtime")
    _writable(runs, "LITMAN_CORE_RUNS_DIR")
    if output is not None: _writable(output, "directorio de salida")
    if input_dir is not None and (not input_dir.is_dir() or not os.access(input_dir, os.R_OK)): raise RuntimeInitializationError("el directorio de entrada no es legible")
def _writable(path: Path, label: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir() or not os.access(path, os.W_OK | os.X_OK): raise RuntimeInitializationError(f"{label} no es escribible: {path}")
