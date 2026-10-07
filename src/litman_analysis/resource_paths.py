from importlib.resources import files
from pathlib import Path


RESOURCE_ROOT = Path(str(files("litman_analysis.resources")))


def resource_path(*parts: str) -> Path:
    return RESOURCE_ROOT.joinpath(*parts)
