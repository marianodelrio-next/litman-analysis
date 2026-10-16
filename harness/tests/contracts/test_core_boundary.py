from __future__ import annotations

import ast
from pathlib import Path


def test_harness_does_not_import_core_implementation() -> None:
    source_root = Path(__file__).parents[2] / "src" / "litman_harness"
    paths = list(source_root.rglob("*.py"))
    assert paths
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
        imported.extend(node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom))
        assert not any(name == "litman_core" or name.startswith("litman_core.") for name in imported), path
