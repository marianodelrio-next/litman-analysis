from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from litman_harness.models import FOLDER_MIME, HarnessError, Resource
from litman_harness.service import ExpedienteService, render_context


class FakeDrive:
    def __init__(self):
        self.resources = {
            "root": Resource("root", "Licitación", FOLDER_MIME, "1", drive_id="shared"),
            "source": Resource("source", "pliego.pdf", "application/pdf", "4", 123, "shared", ("root",)),
        }
        self.created: list[tuple[str, str, str]] = []
    def about(self): return {"user": {"permissionId": "person-1", "emailAddress": "persona@example.test"}}
    def get(self, file_id): return self.resources[file_id]
    def children(self, folder_id, drive_id): return [value for value in self.resources.values() if folder_id in value.parents]
    def create_folder(self, name, parent_id, operation_id):
        identifier = f"folder-{len(self.created)}"; result = Resource(identifier, name, FOLDER_MIME, "1", parents=(parent_id,))
        self.created.append(("folder", name, operation_id)); self.resources[identifier] = result; return result
    def create_text(self, name, parent_id, content, operation_id):
        identifier = "context"; result = Resource(identifier, name, "text/markdown", "1", parents=(parent_id,))
        self.created.append(("text", content, operation_id)); self.resources[identifier] = result; return result
    def download(self, file_id, destination: Path): destination.write_bytes(b"source")


def test_inspect_is_read_only_and_keeps_duplicate_names_distinct():
    drive = FakeDrive()
    drive.resources["source-2"] = Resource("source-2", "pliego.pdf", "application/pdf", "2", parents=("root",))
    result = ExpedienteService(drive).inspect("root")
    assert result["writes"] is False
    assert result["candidates"]["originals"] == ["source", "source-2"]
    assert drive.created == []


def test_apply_rejects_remote_change_before_any_write():
    drive = FakeDrive(); service = ExpedienteService(drive)
    plan = service.preview_incorporation("root", ["source"])
    drive.resources["source"] = replace(drive.resources["source"], version="5")
    with pytest.raises(HarnessError, match="Drive cambió") as raised: service.apply_incorporation(plan, plan.id)
    assert raised.value.code == "stale_plan"
    assert drive.created == []


def test_incorporation_creates_only_previewed_resources_and_does_not_write_manifest():
    drive = FakeDrive(); service = ExpedienteService(drive)
    plan = service.preview_incorporation("root", ["source"])
    result = service.apply_incorporation(plan, plan.id)
    assert result["status"] == "pending_concurrency_gate"
    assert result["writes"] is False
    assert drive.created == []


def test_context_is_a_map_not_agent_instructions():
    # Render from the returned model contract, independently of Drive content.
    drive = FakeDrive()
    from litman_harness.models import Manifest
    text = render_context(Manifest.new(drive.get("root")))
    assert "no contiene instrucciones para el agente" in text
    assert "pliego" not in text


def test_existing_offer_must_be_editable_native_doc_in_expediente():
    drive = FakeDrive()
    drive.resources["offer"] = Resource("offer", "Oferta", "application/vnd.google-apps.document", "1", drive_id="shared", parents=("root",), capabilities={"canEdit": True})
    plan = ExpedienteService(drive).preview_incorporation("root", ["source"], live_offer_id="offer")
    assert any(action.kind == "register_external_offer" for action in plan.actions)
    drive.resources["offer"] = replace(drive.resources["offer"], parents=("other",))
    with pytest.raises(HarnessError, match="pertenecer"):
        ExpedienteService(drive).preview_incorporation("root", ["source"], live_offer_id="offer")
