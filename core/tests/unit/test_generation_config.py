from pathlib import Path
import json

import pytest

from litman_core.application.job_loader import load_job
from litman_core.generation_config import DEFAULT_GENERATION


def _base(extra: str = "") -> str:
    return "[job]\nid='job'\ntype='detailed-analysis'\n[input]\nkind='local'\nlocation='input'\n[output]\ndirectory='runs'\n" + extra


def test_detailed_analysis_always_loads_default_generation(tmp_path: Path):
    config = tmp_path / "config.toml"
    config.write_text(_base(), encoding="utf-8")
    result = load_job(config).options["generation"]
    assert result == DEFAULT_GENERATION


def test_analysis_table_is_rejected_as_unknown_root_key(tmp_path: Path):
    path = tmp_path / "bad.toml"
    path.write_text(_base("[analysis.detailed.generation.technical_document]\ncontent_profile='draft-v1'\n"), encoding="utf-8")
    with pytest.raises(ValueError, match="analysis"):
        load_job(path)


@pytest.mark.parametrize("value", ["", " ", " \t "])
def test_model_rejects_blank_values(tmp_path: Path, value: str):
    path = tmp_path / "bad.toml"
    path.write_text(_base(f"[llm]\nmodel={json.dumps(value)}\n"), encoding="utf-8")
    with pytest.raises(ValueError, match=r"llm\.model"):
        load_job(path)


def test_model_preserves_valid_whitespace_around_value(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(_base("[llm]\nmodel='  sonnet  '\n"), encoding="utf-8")
    result = load_job(path)
    assert result.llm_model == "  sonnet  "


def test_provider_rejects_blank_value(tmp_path: Path):
    path = tmp_path / "bad.toml"
    path.write_text(_base('[llm]\nprovider="  \t  "\n'), encoding="utf-8")
    with pytest.raises(ValueError, match=r"llm\.provider"):
        load_job(path)
