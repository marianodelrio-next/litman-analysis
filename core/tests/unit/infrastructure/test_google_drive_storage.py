from pathlib import Path

import pytest

from litman_core.domain.jobs import JobRequest, JobType, StorageKind
from litman_core.infrastructure.storage.common import publication_inventory
from litman_core.infrastructure.storage.google_drive import GoogleDriveArtifactPublisher, GoogleDriveDocumentSource


class Request:
    def __init__(self, value): self.value = value
    def execute(self):
        if isinstance(self.value, Exception): raise self.value
        return self.value


class Files:
    def __init__(self): self.created = []; self.updated = []; self.deleted = []; self.calls = []
    def get(self, **kwargs): return Request({"id": "source", "mimeType": "application/vnd.google-apps.folder", "trashed": False})
    def list(self, **kwargs): self.calls.append(kwargs); return Request({"files": [{"id": "a", "name": "a.pdf", "mimeType": "application/pdf", "size": "4"}]})
    def get_media(self, **kwargs): return kwargs
    def create(self, **kwargs): self.created.append(kwargs); return Request({"id": f"id-{len(self.created)}", "webViewLink": "drive://file"})
    def update(self, **kwargs): self.updated.append(kwargs); return Request({"id": kwargs["fileId"]})
    def delete(self, **kwargs): self.deleted.append(kwargs); return Request({})


class Service:
    def __init__(self): self.api = Files()
    def files(self): return self.api


def _job() -> JobRequest:
    return JobRequest("job", JobType.ASSESSMENT, StorageKind.GOOGLE_DRIVE, "source", Path("runs"), "destination")


def test_drive_input_uses_shared_drive_flags(tmp_path):
    service = Service()
    def download(_request, stream): stream.write(b"data")
    result = GoogleDriveDocumentSource(service, downloader=download).materialize(_job(), tmp_path)
    assert (result.directory / "a.pdf").is_file()
    assert service.api.calls[0]["supportsAllDrives"] is True


def test_frozen_inventory_is_uploaded_recursively_and_promoted(tmp_path):
    run = tmp_path / "run"; (run / "output").mkdir(parents=True); (run / "logs").mkdir()
    (run / "output/ficha_oportunidad.pdf").write_bytes(b"pdf"); (run / "logs/run.log").write_text("log")
    service = Service(); inventory = publication_inventory(run, JobType.ASSESSMENT, True)
    result = GoogleDriveArtifactPublisher(service, uploader=lambda path: str(path), temporary_suffix=lambda: "fixed").publish_inventory(_job(), "job-20261008T153045.123456Z", inventory, run_dir=run)
    assert {item.name for item in result} == {"output/ficha_oportunidad.pdf", "logs/run.log"}
    assert service.api.updated and service.api.updated[-1]["body"]["name"] == "job-20261008T153045.123456Z"
    roles = {item.name: item.role for item in result}
    assert roles["output/ficha_oportunidad.pdf"] == "opportunity_report"
    assert roles["logs/run.log"] == "run_file"


def test_upload_failure_cleans_temporary_folder(tmp_path):
    run = tmp_path / "run"; (run / "output").mkdir(parents=True); (run / "output/ficha_oportunidad.pdf").write_bytes(b"pdf")
    service = Service(); inventory = publication_inventory(run, JobType.ASSESSMENT, False)
    class BadFiles(Files):
        def create(self, **kwargs):
            self.created.append(kwargs)
            return Request(RuntimeError("boom")) if kwargs.get("media_body") else Request({"id": "tmp"})
    service.api = BadFiles()
    with pytest.raises(RuntimeError):
        GoogleDriveArtifactPublisher(service, uploader=lambda path: str(path)).publish_inventory(_job(), "id", inventory, run_dir=run)
    assert service.api.deleted == [{"fileId": "tmp", "supportsAllDrives": True}]


def test_drive_rejects_symlink_inventory_before_remote_mutation(tmp_path):
    run = tmp_path / "run"; (run / "output").mkdir(parents=True)
    external = tmp_path / "external.pdf"; external.write_bytes(b"pdf")
    (run / "output/ficha_oportunidad.pdf").symlink_to(external)
    service = Service()
    from litman_core.infrastructure.storage.common import CatalogArtifact
    item = CatalogArtifact(run / "output/ficha_oportunidad.pdf", "output/ficha_oportunidad.pdf", "0" * 64, "opportunity_report")
    with pytest.raises(ValueError, match="enlaces simbólicos"):
        GoogleDriveArtifactPublisher(service).publish_inventory(_job(), "id", (item,), run_dir=run)
    assert service.api.created == []
