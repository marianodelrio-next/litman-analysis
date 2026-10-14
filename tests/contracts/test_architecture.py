from __future__ import annotations

from pathlib import Path

import pytest

from litman_core.application.job_loader import load_job
from litman_core.domain.jobs import JobType, StorageKind

ROOT = Path(__file__).parents[2]

def test_deployment_toml_matches_public_loader() -> None:
    example = ROOT / "deployment/config_example.toml"
    job = load_job(example)
    assert job.job_type is JobType.DETAILED_ANALYSIS
    assert job.input_kind is StorageKind.LOCAL


def test_job_loader_rejects_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[job]\nid='job-1'\ntype='assessment'\nunexpected=true\n[input]\nkind='local'\nlocation='input'\n[output]\ndirectory='output'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="job.unexpected"):
        load_job(path)
def test_summary_artifacts_remain_independent_components() -> None:
    from litman_core.generation.bid_preparation_guide import BidPreparationGuideGenerator
    from litman_core.generation.registry import ARTIFACT_GENERATORS
    from litman_core.generation.technical_summary import TechnicalSummaryGenerator

    root = Path(__file__).resolve().parents[2] / "src" / "litman_core" / "generation"
    assert not (root / "bid-preparation-guide").exists()
    assert isinstance(ARTIFACT_GENERATORS["technical-summary"], TechnicalSummaryGenerator)
    assert isinstance(ARTIFACT_GENERATORS["bid-preparation-guide"], BidPreparationGuideGenerator)
    assert ARTIFACT_GENERATORS["technical-summary"].id != ARTIFACT_GENERATORS["bid-preparation-guide"].id
    assert ARTIFACT_GENERATORS["technical-summary"].filename != ARTIFACT_GENERATORS["bid-preparation-guide"].filename
