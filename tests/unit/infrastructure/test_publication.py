from datetime import datetime, timezone

from litman_analysis.infrastructure.storage.publication import publication_folder_name


def test_publication_folder_name_keeps_job_id_and_is_utc_sortable() -> None:
    name = publication_folder_name(
        "job-1", now=lambda: datetime(2026, 10, 8, 15, 30, 45, 123456, tzinfo=timezone.utc),
    )
    assert name == "job-1-20261008T153045.123456Z"
