from __future__ import annotations

import json
from pathlib import Path

import pytest

from litman_harness.adapters.drive import GoogleDriveGateway
from litman_harness.dossier.models import GOOGLE_DOC_MIME, GOOGLE_SHEET_MIME
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
        if "addParents" in kwargs:
            return Request({"id": kwargs["fileId"], "parents": [kwargs["addParents"]]})
        return Request({"id": kwargs["fileId"], **kwargs["body"]})

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


def test_upload_converted_sends_markdown_converted_to_a_google_doc(tmp_path: Path):
    source = tmp_path / "documento.md"
    source.write_text("# Título\n\n- uno\n", encoding="utf-8")
    service = Service()
    GoogleDriveGateway(service).upload_converted("Notas", "offer", source, "text/markdown", "op", "a")
    kwargs = service.files_api.calls[-1][1]
    assert kwargs["body"]["mimeType"] == GOOGLE_DOC_MIME and kwargs["media_body"].mimetype() == "text/markdown"


def test_markdown_upload_matches_the_real_drive_v3_discovery_document(tmp_path: Path):
    source = tmp_path / "documento.md"
    source.write_text("# Título\n", encoding="utf-8")
    document = '{"id": "g", "mimeType": "application/vnd.google-apps.document", "parents": ["f"]}'
    gateway = _real_gateway([({"status": "200"}, document)])
    created = gateway.upload_converted("Notas", "f", source, "text/markdown", "op", "act")
    assert created.id == "g" and created.mime_type == GOOGLE_DOC_MIME


def test_upload_converted_accepts_a_different_target_mime_type(tmp_path: Path):
    source = tmp_path / "datos.xlsx"
    source.write_bytes(b"xlsx")
    service = Service()
    created = GoogleDriveGateway(service).upload_converted(
        "Datos", "folder", source, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "op", "a",
        target_mime_type=GOOGLE_SHEET_MIME)
    body = service.files_api.calls[-1][1]["body"]
    assert body["mimeType"] == GOOGLE_SHEET_MIME and created.mime_type == GOOGLE_SHEET_MIME


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


@pytest.mark.parametrize("reason, code", [("exportSizeLimitExceeded", "export_too_large"),
                                          ("userRateLimitExceeded", "drive_rate_limited"),
                                          ("rateLimitExceeded", "drive_rate_limited"),
                                          ("otherReason", "insufficient_permission")])
def test_drive_403_reasons_are_mapped_to_specific_codes(reason: str, code: str):
    body = json.dumps({"error": {"errors": [{"reason": reason}]}})
    gateway = _real_gateway([({"status": "403"}, body)])
    with pytest.raises(HarnessError) as raised:
        gateway.get("hidden")
    assert raised.value.code == code


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


def test_rename_and_trash_send_the_minimal_update_body():
    service = Service()
    gateway = GoogleDriveGateway(service)
    renamed = gateway.rename("pliego", "nuevo-nombre.pdf")
    name, kwargs = service.files_api.calls[-1]
    assert name == "update" and kwargs["fileId"] == "pliego" and kwargs["body"] == {"name": "nuevo-nombre.pdf"}
    assert renamed.id == kwargs["fileId"]
    trashed = gateway.trash("pliego")
    name, kwargs = service.files_api.calls[-1]
    assert name == "update" and kwargs["fileId"] == "pliego" and kwargs["body"] == {"trashed": True}
    assert trashed.id == kwargs["fileId"]


def test_rename_trash_export_and_conversion_upload_match_the_real_drive_v3_discovery_document(tmp_path: Path):
    from googleapiclient.discovery import build
    from googleapiclient.http import HttpMockSequence
    renamed = '{"id": "p", "name": "nuevo.pdf", "mimeType": "application/pdf", "parents": ["o"]}'
    trashed = '{"id": "p", "trashed": true, "mimeType": "application/pdf", "parents": ["o"]}'
    converted = '{"id": "s", "mimeType": "application/vnd.google-apps.spreadsheet", "parents": ["o"]}'
    http = HttpMockSequence([
        ({"status": "200"}, renamed),
        ({"status": "200"}, trashed),
        ({"status": "200", "content-range": "bytes 0-4/5"}, "texto"),
        ({"status": "200"}, converted),
    ])
    service = build("drive", "v3", http=http, static_discovery=True)
    gateway = GoogleDriveGateway(service)
    assert gateway.rename("p", "nuevo.pdf").name == "nuevo.pdf"
    assert gateway.trash("p").trashed is True
    destination = tmp_path / "doc.pdf"
    gateway.export("doc", "application/pdf", destination)
    assert destination.read_bytes() == b"texto"
    source = tmp_path / "datos.csv"
    source.write_bytes(b"a,b\n1,2\n")
    created = gateway.upload_converted("Datos", "o", source, "text/csv", "op", "act",
                                       target_mime_type="application/vnd.google-apps.spreadsheet")
    assert created.mime_type == "application/vnd.google-apps.spreadsheet"


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


def test_comments_are_listed_page_by_page_without_deleted_ones_against_the_real_discovery_document():
    from urllib.parse import parse_qs, urlparse

    from googleapiclient.discovery import build
    from googleapiclient.http import HttpMockSequence
    first = {"comments": [{"id": "c1", "content": "uno"}], "nextPageToken": "t2"}
    second = {"comments": [{"id": "c2", "content": "dos", "replies": [{"id": "r1"}]}]}
    http = HttpMockSequence([({"status": "200"}, json.dumps(first)), ({"status": "200"}, json.dumps(second))])
    gateway = GoogleDriveGateway(build("drive", "v3", http=http, static_discovery=True))
    assert [item["id"] for item in gateway.comments("file")] == ["c1", "c2"]
    queries = [parse_qs(urlparse(call[0]).query) for call in http.request_sequence]
    assert queries[0]["includeDeleted"] == ["false"] and "pageToken" not in queries[0]
    assert queries[1]["pageToken"] == ["t2"]
    fields = queries[0]["fields"][0]
    for field in ("id", "content", "author(displayName,me)", "createdTime", "resolved", "quotedFileContent(value)",
                  "replies(id,content,author(displayName,me),createdTime,action,deleted)"):
        assert field in fields


def test_comments_stop_on_a_repeated_page_token():
    with pytest.raises(HarnessError) as raised:
        _real_gateway([({"status": "200"}, json.dumps({"comments": [], "nextPageToken": "t"}))] * 3).comments("f")
    assert raised.value.code == "drive_invalid_page"


def test_comments_map_http_errors():
    with pytest.raises(HarnessError) as raised:
        _real_gateway([({"status": "404"}, "{}")]).comments("gone")
    assert raised.value.code == "not_found"


def test_create_comment_and_reply_match_the_real_drive_v3_discovery_document():
    comment = {"id": "c1", "content": "Nuevo", "author": {"displayName": "Yo", "me": True},
              "createdTime": "2026-01-01T00:00:00Z", "resolved": False}
    reply = {"id": "r1", "content": "Hecho", "author": {"displayName": "Yo", "me": True},
            "createdTime": "2026-01-01T00:01:00Z", "action": "resolve", "deleted": False}
    gateway = _real_gateway([({"status": "200"}, json.dumps(comment)), ({"status": "200"}, json.dumps(reply))])
    assert gateway.create_comment("file", "Nuevo") == comment
    assert gateway.create_reply("file", "c1", "Hecho", action="resolve") == reply


def test_export_downloads_a_google_native_file_in_the_requested_format(tmp_path: Path):
    from urllib.parse import parse_qs, urlparse

    from googleapiclient.discovery import build
    from googleapiclient.http import HttpMockSequence
    http = HttpMockSequence([({"status": "200", "content-range": "bytes 0-4/5"}, "texto")])
    gateway = GoogleDriveGateway(build("drive", "v3", http=http, static_discovery=True))
    destination = tmp_path / "out" / "slides.txt"
    gateway.export("slides", "text/plain", destination)
    assert destination.read_bytes() == b"texto"
    uri = http.request_sequence[0][0]
    assert urlparse(uri).path.endswith("/files/slides/export")
    assert parse_qs(urlparse(uri).query)["mimeType"] == ["text/plain"]


def test_resource_carries_modified_time_and_the_new_capabilities():
    from litman_harness.dossier.models import Resource
    item = Resource.from_api({"id": "f", "modifiedTime": "2026-10-01T10:00:00.000Z",
                              "capabilities": {"canRename": True, "canTrash": False, "canComment": True}})
    assert item.modified_time == "2026-10-01T10:00:00.000Z" and item.json()["modified_time"] == item.modified_time
    assert item.capabilities == {"canRename": True, "canTrash": False, "canComment": True}
    assert Resource.from_api({"id": "g", "modifiedTime": 5}).modified_time is None
