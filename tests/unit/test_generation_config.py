from pathlib import Path
import json

import pytest

from litman_core.application.job_loader import load_job


def _base(extra: str = "") -> str:
    return "[job]\nid='job'\ntype='detailed-analysis'\n[input]\nkind='local'\nlocation='input'\n[output]\ndirectory='runs'\n" + extra


def test_generation_preferences_are_loaded_from_unified_toml(tmp_path: Path):
    config = tmp_path / "config.toml"
    config.write_text(_base("[analysis.detailed.generation.technical_document]\ncontent_profile='draft-v1'\n"), encoding="utf-8")
    result = load_job(config).options["generation"]
    assert result["technical_document"]["content_profile"] == "draft-v1"
    assert "artifacts" not in result


@pytest.mark.parametrize("body", ["[analysis.detailed.generation]\nunknown=true\n", "[analysis.detailed.generation.technical_document]\noutput_language='es'\n"])
def test_unified_toml_rejects_unknown_generation_keys_and_types(tmp_path: Path, body: str):
    path = tmp_path / "bad.toml"; path.write_text(_base(body), encoding="utf-8")
    with pytest.raises(ValueError): load_job(path)


@pytest.mark.parametrize("section", ["codex", "llm"])
@pytest.mark.parametrize("value", ["", " ", " \t "])
def test_model_rejects_blank_values(tmp_path: Path, section: str, value: str):
    path = tmp_path / "bad.toml"
    path.write_text(_base(f"[{section}]\nmodel={json.dumps(value)}\n"), encoding="utf-8")
    with pytest.raises(ValueError, match=rf"{section}\.model"):
        load_job(path)


def test_model_preserves_valid_whitespace_around_value(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(_base("[codex]\nmodel='  gpt-test  '\n[llm]\nmodel='  sonnet  '\n"), encoding="utf-8")
    result = load_job(path)
    assert result.codex_model == "  gpt-test  "
    assert result.llm_model == "  sonnet  "


def test_provider_rejects_blank_value(tmp_path: Path):
    path = tmp_path / "bad.toml"
    path.write_text(_base('[llm]\nprovider="  \t  "\n'), encoding="utf-8")
    with pytest.raises(ValueError, match=r"llm\.provider"):
        load_job(path)
