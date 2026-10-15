from __future__ import annotations

import pytest
from fakes import FakeDrive, FakeDriveHttp as Session

from litman_harness.adapters.drive_state import DriveSharedState
from litman_harness.dossier.models import ACTION_MARKER, FOLDER_MIME, OPERATION_MARKER, Resource
from litman_harness.errors import HarnessError


def setup():
    drive = FakeDrive()
    drive.add(Resource("folder", "_LitMan", FOLDER_MIME, "1", drive_id="shared"))
    drive.add(Resource("manifest", "manifest.json", "application/json", "7", drive_id="shared",
                       parents=("folder",)), b'{"a": 1}')
    session = Session(drive)
    return drive, session, DriveSharedState(session, drive)


def test_read_returns_content_with_the_v2_etag_of_a_coherent_snapshot():
    _, session, state = setup()
    assert state.read("manifest") == ('{"a": 1}', '"e1"')
    urls = [(method, url.split("googleapis.com")[1]) for method, url, *_ in session.requests]
    assert urls == [("GET", "/drive/v2/files/manifest"), ("GET", "/drive/v3/files/manifest"),
                    ("GET", "/drive/v2/files/manifest")]


def test_read_retries_while_the_file_changes_and_then_fails():
    _, session, state = setup()
    changes = iter(range(1))

    def change_once(file_id):
        if next(changes, None) is not None:
            session.etags[file_id] += "x"

    session.on_media = change_once
    assert state.read("manifest")[1] == '"e1"x'
    session.on_media = lambda file_id: session.etags.__setitem__(file_id, session.etags[file_id] + "y")
    with pytest.raises(HarnessError) as raised:
        state.read("manifest")
    assert raised.value.code == "concurrent_change"


def test_update_uses_if_match_and_a_stale_etag_never_overwrites():
    drive, session, state = setup()
    _, etag = state.read("manifest")
    state.update_if_version("manifest", '{"a": 2}', etag, "op")
    put = next(item for item in session.requests if item[0] == "PUT")
    assert put[1].endswith("/upload/drive/v2/files/manifest") and put[2]["uploadType"] == "media"
    assert put[3] == {"If-Match": '"e1"', "Content-Type": "application/json"}
    with pytest.raises(HarnessError) as raised:
        state.update_if_version("manifest", '{"a": 3}', etag, "op")
    assert raised.value.code == "concurrent_change" and raised.value.details == {"file_id": "manifest"}
    assert drive.contents["manifest"] == b'{"a": 2}'


def test_create_if_absent_creates_with_markers_then_adopts():
    drive, session, state = setup()
    created = state.create_if_absent("contexto.md", "folder", "# hola\n", "op", "act")
    assert created.app_properties == {OPERATION_MARKER: "op", ACTION_MARKER: "act"}
    assert created.mime_type == "text/markdown" and drive.contents[created.id] == b"# hola\n"
    post = next(item for item in session.requests if item[0] == "POST")
    assert post[2] == {"uploadType": "multipart", "fields": "id", "supportsAllDrives": "true"}
    posts = len([item for item in session.requests if item[0] == "POST"])
    assert state.create_if_absent("contexto.md", "folder", "# hola\n", "op", "act").id == created.id
    assert len([item for item in session.requests if item[0] == "POST"]) == posts


def test_create_if_absent_refuses_duplicates_and_existing_names():
    drive, _, state = setup()
    with pytest.raises(HarnessError) as raised:
        state.create_if_absent("manifest.json", "folder", "{}", "op", "act")
    assert raised.value.code == "already_exists" and raised.value.details == {"file_id": "manifest"}
    markers = {OPERATION_MARKER: "op", ACTION_MARKER: "act"}
    for identifier in ("x", "y"):
        drive.add(Resource(identifier, "contexto.md", "text/markdown", "1", drive_id="shared",
                           parents=("folder",), app_properties=markers))
    with pytest.raises(HarnessError) as raised:
        state.create_if_absent("contexto.md", "folder", "", "op", "act")
    assert raised.value.code == "concurrent_change" and set(raised.value.details["candidates"]) == {"x", "y"}


@pytest.mark.parametrize(("status", "code"), ((401, "oauth_login_required"), (403, "insufficient_permission"),
                                              (404, "not_found"), (500, "drive_error")))
def test_http_errors_use_the_shared_drive_error_map(status, code):
    _, session, state = setup()
    session.status[("GET", "manifest")] = status
    with pytest.raises(HarnessError) as raised:
        state.read("manifest")
    assert raised.value.code == code and raised.value.details == {"http_status": status}
