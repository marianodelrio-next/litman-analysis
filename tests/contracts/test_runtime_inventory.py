from pathlib import Path
import json


def test_forbidden_runtime_names_are_absent_from_current_contracts():
    root = Path(__file__).parents[2]
    forbidden = ("litman-" + "analysis", "litman" + "_analysis", "LITMAN_" + "ANALYSIS_")
    scopes = (root / "src", root / "deployment", root / "docs", root / "README.md")
    paths = []
    for scope in scopes:
        paths.extend(([scope] if scope.is_file() else scope.rglob("*")))
    paths = [
        path
        for path in paths
        if path.is_file()
        and path.suffix != ".pyc"
        and "__pycache__" not in path.parts
        and "local-secrets" not in path.parts
    ]
    offenders = [path for path in paths if any(token in path.read_text(encoding="utf-8", errors="ignore") for token in forbidden)]
    assert offenders == []


def test_historical_artifact_id_is_not_registered_or_documented():
    root = Path(__file__).parents[2]
    from litman_core.generation.registry import ARTIFACT_GENERATORS
    from litman_core.generation_config import APPROVED_ARTIFACTS
    assert set(ARTIFACT_GENERATORS) == set(APPROVED_ARTIFACTS)
    assert "summary" not in ARTIFACT_GENERATORS
    for path in (root / "tests/fixtures", root / "deployment/config.toml", root / "docs"):
        files = [path] if path.is_file() else path.rglob("*")
        for candidate in files:
            if candidate.is_file() and candidate.suffix not in {".pyc", ".pyo"} and "__pycache__" not in candidate.parts:
                text = candidate.read_text(encoding="utf-8", errors="ignore")
                assert '"id": "summary"' not in text
                if candidate.suffix == ".json":
                    document = json.loads(text)
                    artifacts = document.get("options", {}).get("generation", {}).get("artifacts", []) if isinstance(document, dict) else []
                    assert "summary" not in artifacts
