from __future__ import annotations

import json
from pathlib import Path

import pytest

from litman_harness.adapters.docs import GoogleDocsGateway, docs_http_error
from litman_harness.errors import HarnessError

_DISABLED_ERRORS = json.dumps({"error": {"code": 403, "status": "PERMISSION_DENIED", "errors": [
    {"reason": "accessNotConfigured", "domain": "usageLimits", "message": "Docs API has not been used"}]}})
_DISABLED_DETAILS = json.dumps({"error": {"code": 403, "status": "PERMISSION_DENIED", "details": [
    {"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "SERVICE_DISABLED",
     "domain": "googleapis.com", "metadata": {"service": "docs.googleapis.com"}}]}})
_FORBIDDEN = json.dumps({"error": {"code": 403, "errors": [{"reason": "forbidden"}]}})


def _discovery() -> dict:
    import googleapiclient
    path = Path(googleapiclient.__file__).parent / "discovery_cache" / "documents" / "docs.v1.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _gateway(responses):
    from googleapiclient.discovery import build
    from googleapiclient.http import HttpMockSequence
    http = HttpMockSequence(responses)
    return GoogleDocsGateway(build("docs", "v1", http=http, static_discovery=True)), http


def _conforms(schemas: dict, name: str, value) -> None:
    """Every key of ``value`` is a property of the discovery schema ``name``, recursively, with its JSON type."""
    properties = schemas[name]["properties"]
    assert isinstance(value, dict)
    for key, item in value.items():
        assert key in properties, f"{name}.{key} no existe en Docs v1"
        spec = properties[key]
        if "$ref" in spec:
            _conforms(schemas, spec["$ref"], item)
        elif spec.get("type") == "array":
            for element in item:
                if "$ref" in spec["items"]:
                    _conforms(schemas, spec["items"]["$ref"], element)
        elif spec.get("type") == "integer":
            assert isinstance(item, int)
        elif spec.get("type") == "string":
            assert isinstance(item, str)


def test_style_requests_match_the_real_docs_v1_discovery_document():
    span = {"startIndex": 5, "endIndex": 20}
    requests = [
        {"updateParagraphStyle": {"range": span, "paragraphStyle": {"namedStyleType": "HEADING_1"},
                                  "fields": "namedStyleType"}},
        {"updateTextStyle": {"range": span, "textStyle": {"bold": True, "italic": False}, "fields": "bold,italic"}},
        {"createParagraphBullets": {"range": span, "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"}},
        {"createParagraphBullets": {"range": span, "bulletPreset": "NUMBERED_DECIMAL_ALPHA_ROMAN"}},
        {"deleteParagraphBullets": {"range": span}}]
    gateway, _ = _gateway([({"status": "200"}, "echo_request_body")])
    body = gateway.batch_update("doc-1", requests, "rev-1")
    schemas = _discovery()["schemas"]
    _conforms(schemas, "BatchUpdateDocumentRequest", body)
    for request in requests:
        (name, value), = request.items()
        schema = schemas["Request"]["properties"][name]["$ref"]
        _conforms(schemas, schema, value)
    assert {"HEADING_1"} <= set(schemas["ParagraphStyle"]["properties"]["namedStyleType"]["enum"])
    presets = set(schemas["CreateParagraphBulletsRequest"]["properties"]["bulletPreset"]["enum"])
    assert {"BULLET_DISC_CIRCLE_SQUARE", "NUMBERED_DECIMAL_ALPHA_ROMAN"} <= presets


def test_gateway_calls_match_the_real_docs_v1_discovery_document():
    """Build the real Docs v1 client offline: parameters are checked by the client, bodies against the schema."""
    requests = [{"deleteContentRange": {"range": {"startIndex": 5, "endIndex": 9}}},
                {"insertText": {"location": {"index": 5}, "text": "Señor 😀"}}]
    gateway, http = _gateway([({"status": "200"}, json.dumps({"revisionId": "rev-1", "tabs": []})),
                              ({"status": "200"}, "echo_request_body")])
    assert gateway.get("doc-1") == {"revisionId": "rev-1", "tabs": []}
    body = gateway.batch_update("doc-1", requests, "rev-1")
    assert body == {"requests": requests, "writeControl": {"requiredRevisionId": "rev-1"}}
    _conforms(_discovery()["schemas"], "BatchUpdateDocumentRequest", body)
    (get_uri, get_method, _, _), (update_uri, update_method, _, _) = http.request_sequence
    assert get_method == "GET" and "/v1/documents/doc-1?" in get_uri
    assert "suggestionsViewMode=SUGGESTIONS_INLINE" in get_uri and "includeTabsContent=true" in get_uri
    assert "fields=" in get_uri and "tabs" in get_uri
    assert update_method == "POST" and update_uri.split("?")[0].endswith("/v1/documents/doc-1:batchUpdate")


def test_native_comment_calls_match_the_real_docs_v1_discovery_document():
    """Anchored insertion, reply and resolution, and the comment read, as the comment service builds them."""
    requests = [{"insertComment": {"range": {"startIndex": 5, "endIndex": 13, "tabId": "t.0"},
                                   "content": "Revisar 😀"}},
                {"addCommentReply": {"commentId": "kix.1", "post": {"content": "De acuerdo"}}},
                {"addCommentReply": {"commentId": "kix.1", "post": {"commentAction": "RESOLVE"}}}]
    response = {"documentId": "doc-1", "commentUpdateState": "ALL_SAVED",
                "replies": [{"insertComment": {"commentThread": {"commentId": "kix.2", "anchorId": "a.2"}}},
                            {"addCommentReply": {"post": {"postId": "p.1"}}}, {"addCommentReply": {}}],
                "writeControl": {"requiredRevisionId": "rev-1"}}
    gateway, http = _gateway([({"status": "200"}, json.dumps({"revisionId": "rev-1", "comments": []})),
                              ({"status": "200"}, "echo_request_body"),
                              ({"status": "200"}, json.dumps(response))])
    assert gateway.get_with_comments("doc-1") == {"revisionId": "rev-1", "comments": []}
    body = gateway.batch_update_comments("doc-1", requests, "rev-1")
    schemas = _discovery()["schemas"]
    _conforms(schemas, "BatchUpdateDocumentRequest", body)
    assert gateway.batch_update_comments("doc-1", requests, "rev-1") == response
    _conforms(schemas, "BatchUpdateDocumentResponse", response)
    assert set(schemas["Post"]["properties"]["commentAction"]["enum"]) >= {"RESOLVE"}
    assert set(schemas["BatchUpdateDocumentResponse"]["properties"]["commentUpdateState"]["enum"]) >= {
        "ALL_SAVED", "ALL_FAILED_UNKNOWN_REASON"}
    assert {"commentAnchors", "body"} <= set(schemas["DocumentTab"]["properties"])
    assert {"anchorId", "commentId", "headPost", "plainTextQuote", "replies", "status"} <= set(
        schemas["CommentThread"]["properties"])
    get_uri = http.request_sequence[0][0]
    assert "commentsViewMode=COMMENTS_VIEW_MODE_INCLUDED" in get_uri
    assert "suggestionsViewMode=SUGGESTIONS_INLINE" in get_uri and "includeTabsContent=true" in get_uri
    assert "commentAnchors" in get_uri and "comments" in get_uri


def test_a_400_on_a_comment_batch_is_document_changed_only_when_it_blames_the_revision():
    stale = json.dumps({"error": {"code": 400, "status": "FAILED_PRECONDITION", "message": "stale"}})
    named = json.dumps({"error": {"code": 400, "status": "INVALID_ARGUMENT",
                                  "message": "The required revision ID does not match"}})
    invalid = json.dumps({"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "Invalid range"}})
    gateway, _ = _gateway([({"status": "400"}, stale), ({"status": "400"}, named), ({"status": "400"}, invalid),
                           ({"status": "400"}, "not json")])
    codes = []
    for _ in range(4):
        with pytest.raises(HarnessError) as raised:
            gateway.batch_update_comments("doc", [], "rev")
        codes.append(raised.value.code)
        assert raised.value.details == {"http_status": 400}
    assert codes == ["document_changed", "document_changed", "docs_request_rejected", "docs_request_rejected"]


@pytest.mark.parametrize("payload", [_DISABLED_ERRORS, _DISABLED_DETAILS])
@pytest.mark.parametrize("call", ["get", "batch_update"])
def test_disabled_docs_api_is_a_stable_error_with_a_spanish_admin_message(payload, call):
    gateway, _ = _gateway([({"status": "403"}, payload)])
    with pytest.raises(HarnessError) as raised:
        gateway.get("doc") if call == "get" else gateway.batch_update("doc", [], "rev")
    assert raised.value.code == "docs_api_disabled"
    message = str(raised.value)
    assert "administrador" in message and "Google Docs API" in message and "cliente OAuth" in message
    assert raised.value.details == {"http_status": 403}


def test_a_400_on_a_guarded_write_means_the_document_changed():
    gateway, _ = _gateway([({"status": "400"}, json.dumps({"error": {"code": 400, "message": "revision"}})),
                           ({"status": "400"}, json.dumps({"error": {"code": 400}}))])
    with pytest.raises(HarnessError) as raised:
        gateway.batch_update("doc", [], "rev-old")
    assert raised.value.code == "document_changed"
    with pytest.raises(HarnessError) as raised:
        gateway.get("doc")
    assert raised.value.code == "docs_error"


@pytest.mark.parametrize("status, payload, code", [
    (401, "", "oauth_login_required"), (403, _FORBIDDEN, "insufficient_permission"),
    (404, '{"error": {"code": 404}}', "not_found"), (500, "not json", "docs_error")])
def test_other_docs_http_errors_map_like_drive_but_name_google_docs(status, payload, code):
    gateway, _ = _gateway([({"status": str(status)}, payload)])
    with pytest.raises(HarnessError) as raised:
        gateway.get("doc")
    assert raised.value.code == code and raised.value.details == {"http_status": status}
    if status in (403, 404):
        assert "Google Docs" in str(raised.value)


def test_error_reasons_are_read_from_bytes_and_malformed_bodies_are_ignored():
    assert docs_http_error(403, _DISABLED_DETAILS.encode()).code == "docs_api_disabled"
    for content in (None, b"", b"[]", b'{"error": "x"}', b'{"error": {"errors": ["x", {"reason": 3}]}}'):
        assert docs_http_error(403, content).code == "insufficient_permission"
