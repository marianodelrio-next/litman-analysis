from pathlib import Path

import pytest

from litman_core.application.job_loader import load_job


def _base(extra: str = "") -> str:
    return "[job]\nid='job'\ntype='detailed-analysis'\n[input]\nkind='local'\nlocation='input'\n[output]\ndirectory='runs'\n" + extra


def test_generation_preferences_are_loaded_from_unified_toml(tmp_path: Path):
    config = tmp_path / "config.toml"
    config.write_text(_base("[analysis.detailed.generation.technical_document]\noutput_language='es'\n"), encoding="utf-8")
    result = load_job(config).options["generation"]
    assert result["technical_document"]["output_language"] == "es"
    assert "artifacts" not in result


@pytest.mark.parametrize("body", ["[analysis.detailed.generation]\nunknown=true\n", "[analysis.detailed.generation.technical_document]\noutput_language=1\n"])
def test_unified_toml_rejects_unknown_generation_keys_and_types(tmp_path: Path, body: str):
    path = tmp_path / "bad.toml"; path.write_text(_base(body), encoding="utf-8")
    with pytest.raises(ValueError): load_job(path)
