from __future__ import annotations

from pathlib import Path

import pytest

from litman_harness.adapters.drive import GoogleDriveGateway
from litman_harness.dossier.models import GOOGLE_DOC_MIME
from litman_harness.errors import HarnessError


class Request:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


class Files:
    def __init__(self):
        self.calls = []

    def get(self, **kwargs):
        self.calls.append(("get", kwargs))
        return Request({"id": kwargs["fileId"], "mimeType": "application/vnd.google-apps.folder", "driveId": "d"})

    def list(self, **kwargs):
        self.calls.append(("list", kwargs))
        return Request({"files": [
            {"id": "a", "name": "x", "appProperties": {"litman_operation_id": "op", "litman_action_id": "act"}},
            {"id": "b", "name": "x", "appProperties": {"litman_operation_id": "op", "litman_action_id": "other"}}]})

    def update(self, **kwargs):
        self.calls.append(("update", kwargs))
        return Request({"id": kwargs["fileId"], "parents": [kwargs["addParents"]]})

    def copy(self, **kwargs):
        self.calls.append(("copy", kwargs))
        return Request({"id": "copy", "name": kwargs["body"]["name"], "parents": kwargs["body"]["parents"],
                        "appProperties": kwargs["body"]["appProperties"]})

    def create(self, **kwargs):
        self.calls.append(("create", kwargs))
        return Request({"id": "new", "mimeType": kwargs["body"].get("mimeType", "application/pdf"),
                        "parents": kwargs["body"]["parents"], "appProperties": kwargs["body"]["appProperties"]})


class Service:
    def __init__(self):
        self.files_api = Files()

    def files(self):
        return self.files_api


def test_find_by_markers_searches_only_the_parent_and_filters_exactly():
    service = Service()
    found = GoogleDriveGateway(service).find_by_markers("parent", "op", "act")
    assert [item.id for item in found] == ["a"]
    query = next(kwargs for name, kwargs in service.files_api.calls if name == "list")
    assert query["q"].startswith("'parent' in parents and trashed = false")
    assert "value='op'" in query["q"] and "value='act'" in query["q"]
    assert query["corpora"] == "drive" and query["driveId"] == "d"


def test_upload_converted_creates_google_doc_directly_in_destination(tmp_path: Path):
    source = tmp_path / "memoria.docx"
    source.write_bytes(b"docx")
    service = Service()
    created = GoogleDriveGateway(service).upload_converted("Memoria", "offer", source, "application/docx", "op", "a")
    body = service.files_api.calls[-1][1]["body"]
    assert body["mimeType"] == GOOGLE_DOC_MIME and body["parents"] == ["offer"]
    assert created.app_properties == {"litman_operation_id": "op", "litman_action_id": "a"}


def test_create_document_creates_an_empty_google_doc_with_markers():
    service = Service()
    created = GoogleDriveGateway(service).create_document("Notas", "offer", "op", "a")
    name, kwargs = service.files_api.calls[-1]
    assert name == "create" and "media_body" not in kwargs and kwargs["supportsAllDrives"] is True
    assert kwargs["body"] == {"name": "Notas", "mimeType": GOOGLE_DOC_MIME, "parents": ["offer"],
                              "appProperties": {"litman_operation_id": "op", "litman_action_id": "a"}}
    assert created.mime_type == GOOGLE_DOC_MIME and created.has_markers("op", "a")


def test_gateway_calls_match_the_real_drive_v3_discovery_document(tmp_path: Path):
    """Build the real Drive v3 client offline so every parameter is validated by the API schema."""
    from googleapiclient.discovery import build
    from googleapiclient.http import HttpMockSequence

    folder = '{"id": "f", "mimeType": "application/vnd.google-apps.folder", "driveId": "d"}'
    created = '{"id": "n", "mimeType": "application/vnd.google-apps.folder", "parents": ["f"]}'
    document = '{"id": "g", "mimeType": "application/vnd.google-apps.document", "parents": ["f"]}'
    http = HttpMockSequence([
        ({"status": "200"}, '{"user": {"permissionId": "p"}}'),
        ({"status": "200"}, folder),
        ({"status": "200"}, '{"files": []}'),
        ({"status": "200"}, folder),
        ({"status": "200"}, '{"files": []}'),
        ({"status": "200"}, created),
        ({"status": "200"}, document),
    ])
    service = build("drive", "v3", http=http, static_discovery=True)
    gateway = GoogleDriveGateway(service)
    assert gateway.about() == {"user": {"permissionId": "p"}}
    assert gateway.get("f").id == "f"
    assert gateway.children("f", "d") == []
    assert gateway.find_by_markers("f", "op", "act") == []
    assert gateway.create_folder("Oferta", "f", "op", "act").id == "n"
    assert gateway.create_document("Notas", "f", "op", "act").id == "g"


def _real_gateway(responses):
    from googleapiclient.discovery import build
    from googleapiclient.http import HttpMockSequence
    return GoogleDriveGateway(build("drive", "v3", http=HttpMockSequence(responses), static_discovery=True))


@pytest.mark.parametrize("status, code", [("404", "not_found"), ("403", "insufficient_permission"),
                                          ("401", "oauth_login_required"), ("500", "drive_error")])
def test_drive_http_errors_become_stable_harness_errors(status: str, code: str):
    gateway = _real_gateway([({"status": status}, '{"error": {"message": "x"}}')])
    with pytest.raises(HarnessError) as raised:
        gateway.get("hidden")
    assert raised.value.code == code
    assert raised.value.details == {"http_status": int(status)}


def test_inaccessible_parent_does_not_break_membership():
    from litman_harness.dossier.membership import belongs_to_root
    from litman_harness.dossier.models import FOLDER_MIME, Resource
    gateway = _real_gateway([({"status": "404"}, '{"error": {"message": "x"}}')])
    root = Resource("root", "Licitación", FOLDER_MIME, "1", drive_id="d")
    item = Resource("file", "pliego.pdf", "application/pdf", "1", drive_id="d", parents=("hidden",))
    assert belongs_to_root(gateway, root, item) is False


def test_gateway_requests_only_the_capabilities_it_checks():
    service = Service()
    GoogleDriveGateway(service).get("f")
    fields = service.files_api.calls[0][1]["fields"]
    assert ("capabilities(canListChildren,canAddChildren,canDownload,canEdit,canMoveItemWithinDrive,canCopy,"
            "canRename,canTrash,canComment)" in fields)
    assert fields.endswith(",md5Checksum,modifiedTime")


def test_move_changes_parents_and_copy_carries_markers_into_destination():
    service = Service()
    gateway = GoogleDriveGateway(service)
    moved = gateway.move("pliego", "originales", ("root",))
    name, kwargs = service.files_api.calls[-1]
    assert name == "update" and kwargs["addParents"] == "originales" and kwargs["removeParents"] == "root"
    assert kwargs["body"] == {} and kwargs["supportsAllDrives"] is True
    assert moved.id == "pliego" and moved.parents == ("originales",)
    copied = gateway.copy("pliego", "pliego.pdf", "originales", "op", "act")
    name, kwargs = service.files_api.calls[-1]
    assert name == "copy" and kwargs["fileId"] == "pliego" and kwargs["supportsAllDrives"] is True
    assert kwargs["body"] == {"name": "pliego.pdf", "parents": ["originales"],
                              "appProperties": {"litman_operation_id": "op", "litman_action_id": "act"}}
    assert copied.id == "copy" and copied.has_markers("op", "act")


def test_move_and_copy_match_the_real_drive_v3_discovery_document():
    moved = '{"id": "p", "mimeType": "application/pdf", "parents": ["o"]}'
    copied = '{"id": "c", "mimeType": "application/pdf", "parents": ["o"]}'
    gateway = _real_gateway([({"status": "200"}, moved), ({"status": "200"}, copied),
                             ({"status": "403"}, '{"error": {"message": "x"}}')])
    assert gateway.move("p", "o", ("root",)).parents == ("o",)
    assert gateway.copy("p", "pliego.pdf", "o", "op", "act").id == "c"
    with pytest.raises(HarnessError) as raised:
        gateway.move("p", "o", ("root",))
    assert raised.value.code == "insufficient_permission"
