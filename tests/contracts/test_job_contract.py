from pathlib import Path

import pytest

from litman_core.application.job_loader import load_job
from litman_core.domain.jobs import JobRequest, StorageKind


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
