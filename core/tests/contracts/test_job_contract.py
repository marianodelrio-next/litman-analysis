from pathlib import Path

import pytest

from litman_core.application.job_loader import load_job
from litman_core.domain.jobs import JobRequest, JobType, StorageKind

ROOT = Path(__file__).parents[2]
MINIMAL_TOML = ROOT.parent / "docs/contracts/core-config.minimal.toml"
COMPLETE_TOML = ROOT / "deployment/config_example.toml"


def _write(path: Path, extra: str = "") -> None:
    path.write_text(
        "[job]\nid = \"a\"\ntype = \"assessment\"\n\n"
        "[input]\nkind = \"google-drive\"\nlocation = \"folder-id\"\n\n"
        "[output]\ndirectory = \"runs\"\n" + extra,
        encoding="utf-8",
    )


def test_drive_input_and_relative_output_load_from_toml(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"; _write(path)
    request = load_job(path)
    assert request.input_kind is StorageKind.GOOGLE_DRIVE
    assert request.input_location == "folder-id"
    assert request.output_directory == tmp_path / "runs"


def test_toml_rejects_unknown_input_key_and_removed_job_fields(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "[job]\nid='a'\ntype='assessment'\n[input]\nkind='google-drive'\n"
        "location='folder-id'\ndocuments=[]\n[output]\ndirectory='runs'\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="input.documents"):
        load_job(path)
    assert "documents" not in JobRequest.__dataclass_fields__


def test_minimal_template_loads(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(MINIMAL_TOML.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "input").mkdir()
    job = load_job(config)
    assert job.job_type is JobType.DETAILED_ANALYSIS
    assert job.input_kind is StorageKind.LOCAL
    assert job.llm_provider == "codex"
    assert job.job_id == "input"


def test_complete_template_loads() -> None:
    job = load_job(COMPLETE_TOML)
    assert job.job_type is JobType.DETAILED_ANALYSIS
    assert job.input_kind is StorageKind.LOCAL


def test_job_id_defaults_to_input_folder_name_when_local(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    (tmp_path / "caso-123").mkdir()
    config.write_text(
        "[job]\ntype='assessment'\n[input]\nlocation='caso-123'\n[output]\ndirectory='runs'\n",
        encoding="utf-8",
    )
    job = load_job(config)
    assert job.job_id == "caso-123"


def test_job_id_defaults_to_drive_location_when_google_drive(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        "[job]\ntype='assessment'\n[input]\nkind='google-drive'\nlocation='folder-id'\n[output]\ndirectory='runs'\n",
        encoding="utf-8",
    )
    job = load_job(config)
    assert job.job_id == "folder-id"


def test_job_id_default_is_sanitized_to_the_public_pattern(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    (tmp_path / " caso raro!").mkdir()
    config.write_text(
        "[job]\ntype='assessment'\n[input]\nlocation=' caso raro!'\n[output]\ndirectory='runs'\n",
        encoding="utf-8",
    )
    job = load_job(config)
    assert job.job_id == "caso-raro-"


def test_input_kind_defaults_to_local(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    (tmp_path / "input").mkdir()
    config.write_text(
        "[job]\ntype='assessment'\n[input]\nlocation='input'\n[output]\ndirectory='runs'\n",
        encoding="utf-8",
    )
    job = load_job(config)
    assert job.input_kind is StorageKind.LOCAL


def test_analysis_table_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        "[job]\ntype='detailed-analysis'\n[input]\nlocation='input'\n[output]\ndirectory='runs'\n"
        "[analysis]\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="analysis"):
        load_job(config)


def test_unknown_root_key_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        "[job]\ntype='assessment'\n[input]\nlocation='input'\n[output]\ndirectory='runs'\n"
        "[unexpected]\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unexpected"):
        load_job(config)
