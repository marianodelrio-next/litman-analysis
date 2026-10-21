from __future__ import annotations

from pathlib import Path

import pytest

from litman_harness.adapters.metadata import MetadataDocsGateway, MetadataGateway, MetadataSheetsGateway
from litman_harness.errors import HarnessError


def test_metadata_gateway_is_read_only(harness_env, tmp_path):
    gateway = MetadataGateway(Path(harness_env["LITMAN_HARNESS_METADATA"]))
    assert [item.id for item in gateway.children("root", "shared")] == ["source"]
    for call in (lambda: gateway.create_folder("x", "root", "op"),
                 lambda: gateway.create_document("x", "root", "op", "act"), lambda: gateway.download("source", tmp_path / "x"),
                 lambda: gateway.move("source", "folder", ("root",)),
                 lambda: gateway.copy("source", "x", "folder", "op", "act"),
                 lambda: gateway.rename("source", "x"), lambda: gateway.trash("source"),
                 lambda: gateway.export("source", "text/plain", tmp_path / "x"),
                 lambda: gateway.comments("source")):
        with pytest.raises(HarnessError) as raised:
            call()
        assert raised.value.code == "read_only_adapter"


def test_metadata_docs_gateway_neither_reads_nor_writes():
    gateway = MetadataDocsGateway()
    for call in (lambda: gateway.get("doc"), lambda: gateway.batch_update("doc", [], "rev"),
                 lambda: gateway.get_with_comments("doc"), lambda: gateway.batch_update_comments("doc", [], "rev")):
        with pytest.raises(HarnessError) as raised:
            call()
        assert raised.value.code == "read_only_adapter"


def test_metadata_sheets_gateway_neither_reads_nor_writes():
    gateway = MetadataSheetsGateway()
    for call in (lambda: gateway.get("sheet"), lambda: gateway.values("sheet", ["'A'"]),
                 lambda: gateway.values("sheet", ["'A'"], "UNFORMATTED_VALUE")):
        with pytest.raises(HarnessError) as raised:
            call()
        assert raised.value.code == "read_only_adapter"


def test_unreadable_metadata_is_a_configuration_error(tmp_path):
    with pytest.raises(HarnessError) as raised:
        MetadataGateway(tmp_path / "missing.json")
    assert raised.value.code == "adapter_not_configured"
