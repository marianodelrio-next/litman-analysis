from pathlib import Path

import pytest

from litman_core.generation_config import load_generation_config, merge_generation


def test_toml_and_job_precedence(tmp_path: Path):
    config = tmp_path / "config.toml"
    config.write_text('[analysis.detailed.generation]\nartifacts=["technical-summary"]\n[analysis.detailed.generation.technical_document]\noutput_language="es"\n', encoding="utf-8")
    result = merge_generation(load_generation_config(config), {"technical_document": {"output_language": "auto"}})
    assert result["artifacts"] == ["technical-summary"]
    assert result["technical_document"]["output_language"] == "auto"


@pytest.mark.parametrize("body", ["[analysis.detailed.generation]\nunknown=true\n", "[analysis.detailed.generation]\nartifacts=1\n"])
def test_toml_rejects_unknown_keys_and_types(tmp_path: Path, body: str):
    path = tmp_path / "bad.toml"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(ValueError):
        load_generation_config(path)


def test_toml_rejects_unknown_root_tables(tmp_path: Path):
    path = tmp_path / "bad-root.toml"
    path.write_text("[project]\nname='bad'\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_generation_config(path)
