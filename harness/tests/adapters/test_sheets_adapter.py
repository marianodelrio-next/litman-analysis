from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from litman_harness.adapters.google_errors import reasons
from litman_harness.adapters.sheets import GoogleSheetsGateway, sheets_http_error
from litman_harness.errors import HarnessError

_DISABLED_ERRORS = json.dumps({"error": {"code": 403, "status": "PERMISSION_DENIED", "errors": [
    {"reason": "accessNotConfigured", "domain": "usageLimits", "message": "Sheets API has not been used"}]}})
_DISABLED_DETAILS = json.dumps({"error": {"code": 403, "status": "PERMISSION_DENIED", "details": [
    {"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "SERVICE_DISABLED",
     "domain": "googleapis.com", "metadata": {"service": "sheets.googleapis.com"}}]}})
_FORBIDDEN = json.dumps({"error": {"code": 403, "errors": [{"reason": "forbidden"}]}})


def _discovery() -> dict:
    import googleapiclient
    path = Path(googleapiclient.__file__).parent / "discovery_cache" / "documents" / "sheets.v4.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _gateway(responses):
    from googleapiclient.discovery import build
    from googleapiclient.http import HttpMockSequence
    http = HttpMockSequence(responses)
    return GoogleSheetsGateway(build("sheets", "v4", http=http, static_discovery=True)), http


def test_gateway_calls_match_the_real_sheets_v4_discovery_document():
    """Build the real Sheets v4 client offline: the client validates every parameter against the API schema."""
    structure = {"sheets": [{"properties": {"sheetId": 0, "title": "Hoja 1",
                                            "gridProperties": {"rowCount": 1000, "columnCount": 26}}}]}
    ranges = {"spreadsheetId": "s", "valueRanges": [{"range": "'Hoja 1'!A1:B2", "values": [["a", "b"]]}]}
    gateway, http = _gateway([({"status": "200"}, json.dumps(structure)), ({"status": "200"}, json.dumps(ranges))])
    assert gateway.get("s") == structure
    assert gateway.values("s", ["'Hoja 1'", "'O''Brien'"]) == ranges["valueRanges"]
    (get_uri, get_method, *_), (values_uri, *_) = http.request_sequence
    get_query, values_query = (parse_qs(urlparse(uri).query) for uri in (get_uri, values_uri))
    assert get_method == "GET" and urlparse(get_uri).path.endswith("/spreadsheets/s")
    assert get_query["fields"] == ["sheets(properties(sheetId,title,gridProperties(rowCount,columnCount)))"]
    assert urlparse(values_uri).path.endswith("/spreadsheets/s/values:batchGet")
    assert values_query["ranges"] == ["'Hoja 1'", "'O''Brien'"]
    assert values_query["valueRenderOption"] == ["FORMATTED_VALUE"]
    assert set(_discovery()["schemas"]["BatchGetValuesResponse"]["properties"]) >= {"valueRanges"}


def test_gateway_sends_the_given_render_option():
    gateway, http = _gateway([({"status": "200"}, json.dumps({"valueRanges": []}))])
    assert gateway.values("s", ["'A'"], "UNFORMATTED_VALUE") == []
    assert parse_qs(urlparse(http.request_sequence[0][0]).query)["valueRenderOption"] == ["UNFORMATTED_VALUE"]


def test_gateway_ignores_malformed_value_ranges():
    gateway, _ = _gateway([({"status": "200"}, json.dumps({"valueRanges": [{"values": [["a"]]}, "x", None]}))])
    assert gateway.values("s", ["'A'"]) == [{"values": [["a"]]}]


@pytest.mark.parametrize("status, code", [("404", "not_found"), ("403", "insufficient_permission"),
                                          ("401", "oauth_login_required"), ("500", "sheets_error")])
def test_sheets_http_errors_become_stable_harness_errors(status: str, code: str):
    gateway, _ = _gateway([({"status": status}, '{"error": {"message": "x"}}')])
    with pytest.raises(HarnessError) as raised:
        gateway.get("hidden")
    assert raised.value.code == code and raised.value.details["http_status"] == int(status)


@pytest.mark.parametrize("body", [_DISABLED_ERRORS, _DISABLED_DETAILS])
def test_a_disabled_sheets_api_is_reported_to_the_administrator(body: str):
    gateway, _ = _gateway([({"status": "403"}, body)])
    with pytest.raises(HarnessError) as raised:
        gateway.values("s", ["'A'"])
    assert raised.value.code == "sheets_api_disabled" and "Google Sheets" in str(raised.value)


def test_other_forbidden_reasons_and_malformed_bodies_stay_a_permission_error():
    assert sheets_http_error(403, _FORBIDDEN).code == "insufficient_permission"
    assert sheets_http_error(403, _DISABLED_DETAILS.encode()).code == "sheets_api_disabled"
    for content in (None, b"", b"[]", b'{"error": "x"}', b'{"error": {"errors": ["x", {"reason": 3}]}}'):
        assert sheets_http_error(403, content).code == "insufficient_permission"


def test_error_reasons_are_shared_by_every_google_adapter():
    assert reasons(_DISABLED_ERRORS) == {"accessNotConfigured"} and reasons(_DISABLED_DETAILS) == {"SERVICE_DISABLED"}
    assert reasons(b"not json") == set()
